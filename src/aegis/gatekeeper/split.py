"""Zaman sıralı bölme ve etiket gecikmesi tamponu (FR-10, #14).

D1 satırları commit zamanına (`as_of`) göre üçe ayrılır: eğitim < doğrulama < test. Rastgele
bölme yoktur; bir model yalnızca kendinden önceki dönemle eğitilir ve sonraki dönemde sınanır.

İki koruma birlikte uygulanır:

1. **Tampon:** Bir kümenin bitişinden önceki `label_delay_days` günün commit'leri o kümeye
   alınmaz. Bu commit'lerin hataları o tarihte henüz bulunmamış olabilir.
2. **Bilinen etiket:** Eğitim ve doğrulama kümelerinde bir commit yalnızca hatası kümenin
   kullanıldığı andan *önce* düzeltilmişse `buggy` sayılır (`fixed_at < sınır`). Böylece
   gelecekte bulunacak bir hata geçmişe sızmaz. Test kümesi son (en iyi bilinen) etiketi kullanır.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

from aegis.config import TrainingConfig


@dataclass(frozen=True)
class Split:
    train: pl.DataFrame
    valid: pl.DataFrame
    test: pl.DataFrame
    valid_start: datetime
    test_start: datetime


def labels_as_of(frame: pl.DataFrame, when: datetime) -> pl.DataFrame:
    """`buggy`ı `when` anında bilinene indirger: hata yalnızca `when`'den önce düzeltildiyse."""
    return frame.with_columns(
        (pl.col("fixed_at").is_not_null() & (pl.col("fixed_at") < when)).alias("buggy")
    )


def time_split(d1: pl.DataFrame, config: TrainingConfig | None = None) -> Split:
    """Tek bir reponun D1 satırlarını zaman sırasıyla eğitim/doğrulama/test olarak böler."""
    config = config or TrainingConfig()
    if d1.height < 3:
        raise ValueError("bölmek için en az 3 commit gerekir")
    rows = d1.sort("as_of", maintain_order=True)
    n = rows.height
    test_at = n - max(1, round(n * config.test_fraction))
    valid_at = test_at - max(1, round(n * config.valid_fraction))
    if valid_at <= 0:
        raise ValueError("eğitim kümesi boş kalıyor; payları küçültün")
    valid_start: datetime = rows["as_of"][valid_at]
    test_start: datetime = rows["as_of"][test_at]
    delay = timedelta(days=config.label_delay_days)

    train = rows.filter(pl.col("as_of") < valid_start - delay)
    valid = rows.filter((pl.col("as_of") >= valid_start) & (pl.col("as_of") < test_start - delay))
    test = rows.filter(pl.col("as_of") >= test_start)
    if train.height == 0 or valid.height == 0:
        raise ValueError(
            f"{config.label_delay_days} günlük tampon eğitim ya da doğrulama kümesini boşaltıyor; "
            "label_delay_days'i küçültün ya da daha uzun bir geçmiş kullanın"
        )
    return Split(
        train=labels_as_of(train, valid_start),
        valid=labels_as_of(valid, test_start),
        test=test,
        valid_start=valid_start,
        test_start=test_start,
    )


def cross_split(d1: pl.DataFrame, target: str, config: TrainingConfig | None = None) -> Split:
    """Repolar arası (leave-one-project-out) bölme (FR-15, #17).

    Test kümesi, hedef reponun kendi `time_split` test kümesiyle aynıdır; böylece repo içi ve
    repolar arası sonuçlar aynı commit'ler üzerinde karşılaştırılır. Model yalnızca *diğer*
    repoların, hedefin test döneminden (tampon dahil) önceki commit'leriyle eğitilir: hedef
    reponun hiç geçmişi yokmuş gibi (soğuk başlangıç), ama gelecekten bilgi sızmadan. Bu havuz
    zaman sırasıyla eğitim ve doğrulama olarak ikiye ayrılır; eşik doğrulamada seçilir.
    """
    config = config or TrainingConfig()
    own = time_split(d1.filter(pl.col("repo") == target), config)
    delay = timedelta(days=config.label_delay_days)
    pool = d1.filter((pl.col("repo") != target) & (pl.col("as_of") < own.test_start - delay)).sort(
        "as_of", maintain_order=True
    )
    if pool.height < 2:
        raise ValueError(f"{target} dışında, test döneminden önce yeterli commit yok")
    # Repo içi bölmedeki eğitim:doğrulama oranı korunur.
    share = config.valid_fraction / (1 - config.test_fraction)
    valid_at = pool.height - max(1, round(pool.height * share))
    valid_start: datetime = pool["as_of"][valid_at]
    train = pool.filter(pl.col("as_of") < valid_start - delay)
    valid = pool.filter(pl.col("as_of") >= valid_start)
    if train.height == 0:
        raise ValueError("tampon, repolar arası eğitim kümesini boşaltıyor")
    return Split(
        train=labels_as_of(train, valid_start),
        valid=labels_as_of(valid, own.test_start),
        test=own.test,
        valid_start=valid_start,
        test_start=own.test_start,
    )
