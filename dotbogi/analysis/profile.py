"""컬럼 하나의 프로필: 기본 통계(train/test), 분포 비교 그림 데이터, 분포 차이 지표, 타깃과의 관계."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ..utils import as_label, sample_index, to_float
from .common import category_codes, oof_power, quantile_codes

TOP_K = 20


# ───────────────────────────── 기본 통계
def numeric_stats(x: np.ndarray) -> dict:
    n = len(x)
    finite = x[np.isfinite(x)]
    out = {"count": n, "missing": int(n - finite.size), "missing_rate": (n - finite.size) / n if n else 0.0}
    if finite.size == 0:
        return out
    q = np.quantile(finite, [0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0])
    iqr = q[4] - q[2]
    lo, hi = q[2] - 1.5 * iqr, q[4] + 1.5 * iqr
    out.update({
        "mean": float(finite.mean()), "std": float(finite.std(ddof=1)) if finite.size > 1 else 0.0,
        "min": float(q[0]), "p01": float(q[1]), "p25": float(q[2]), "median": float(q[3]),
        "p75": float(q[4]), "p99": float(q[5]), "max": float(q[6]),
        "zeros_rate": float((finite == 0).mean()),
        "negative_rate": float((finite < 0).mean()),
        "outlier_rate": float(((finite < lo) | (finite > hi)).mean()) if iqr > 0 else 0.0,
        "skew": float(stats.skew(finite[: 500_000])) if finite.size > 2 and finite.std() > 0 else 0.0,
        "n_unique": int(np.unique(finite[: 2_000_000]).size),
    })
    return out


def categorical_stats(s: pd.Series) -> dict:
    n = len(s)
    miss = int(s.isna().sum())
    vc = s.value_counts(dropna=True)
    out = {"count": n, "missing": miss, "missing_rate": miss / n if n else 0.0, "n_unique": int(vc.size)}
    if vc.size:
        out["top"] = [{"value": as_label(k), "count": int(v), "rate": v / n} for k, v in vc.head(5).items()]
        out["top1_rate"] = float(vc.iloc[0] / n)
        out["singleton_rate"] = float((vc == 1).sum() / vc.size)
    return out


def datetime_stats(s: pd.Series) -> dict:
    n = len(s)
    miss = int(s.isna().sum())
    out = {"count": n, "missing": miss, "missing_rate": miss / n if n else 0.0}
    nn = s.dropna()
    if len(nn):
        out.update({"min": nn.min().isoformat(), "max": nn.max().isoformat(), "n_unique": int(nn.nunique())})
    return out


# ───────────────────────────── 분포 차이 지표
def psi(p: np.ndarray, q: np.ndarray, eps: float = 1e-4) -> float:
    """Population Stability Index. p=train 비율, q=test 비율."""
    p = np.clip(p, eps, None)
    q = np.clip(q, eps, None)
    p, q = p / p.sum(), q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def drift_level(psi_value: float | None) -> str:
    if psi_value is None or not np.isfinite(psi_value):
        return "unknown"
    if psi_value < 0.1:
        return "stable"
    if psi_value < 0.25:
        return "watch"
    return "shift"


# ───────────────────────────── 프로필
def profile_column(name: str, kind: str, discrete: bool,
                   tr: pd.Series | None, te: pd.Series | None,
                   y: np.ndarray | None = None, y_mask: np.ndarray | None = None,
                   task: str | None = None, classes: list | None = None,
                   with_power: bool = True) -> dict:
    """화면 한 장에 필요한 모든 것. y는 train과 같은 길이의 인코딩된 타깃."""
    out: dict = {"name": name, "kind": kind, "discrete": discrete}
    if kind == "text":
        # 문장은 값 자체를 비교하면 의미가 없어서 '글자 수'로 분포·차이·타깃 관계를 본다.
        out["basis"] = "length"
        tr = tr.astype("string").str.len().astype("float64") if tr is not None else None
        te = te.astype("string").str.len().astype("float64") if te is not None else None
        kind = "numeric"
        discrete = False
    as_cat = kind in ("categorical", "binary", "id", "constant") or (kind == "numeric" and discrete)

    if kind == "datetime":
        from ..schema import to_datetime_safe
        trd = to_datetime_safe(tr) if tr is not None else None
        ted = to_datetime_safe(te) if te is not None else None
        out["train"] = datetime_stats(trd) if trd is not None else None
        out["test"] = datetime_stats(ted) if ted is not None else None
        trn = to_float(trd) if trd is not None else None
        ten = to_float(ted) if ted is not None else None
        out["dist"] = _numeric_dist(trn, ten, datetime=True)
        out["drift"] = _numeric_drift(trn, ten)
        if trn is not None and y is not None:
            out["target"] = _numeric_target(trn, y, y_mask, task, classes, datetime=True)
        if with_power and trn is not None and y is not None:
            out["power"] = _power(quantile_codes(trn, 20)[0], y, y_mask, task)
        return out

    if as_cat:
        out["train"] = categorical_stats(tr) if tr is not None else None
        out["test"] = categorical_stats(te) if te is not None else None
        if kind == "numeric":  # 이산형 숫자는 숫자 통계도 같이
            out["train_num"] = numeric_stats(to_float(tr)) if tr is not None else None
            out["test_num"] = numeric_stats(to_float(te)) if te is not None else None
        out["dist"] = _categorical_dist(tr, te, numeric_order=kind == "numeric")
        out["drift"] = _categorical_drift(tr, te)
        if tr is not None and y is not None:
            out["target"] = _categorical_target(tr, y, y_mask, task, classes)
        if with_power and tr is not None and y is not None:
            out["power"] = _power(category_codes(tr)[0], y, y_mask, task)
        return out

    trn = to_float(tr) if tr is not None else None
    ten = to_float(te) if te is not None else None
    out["train"] = numeric_stats(trn) if trn is not None else None
    out["test"] = numeric_stats(ten) if ten is not None else None
    out["dist"] = _numeric_dist(trn, ten)
    out["drift"] = _numeric_drift(trn, ten)
    if trn is not None and y is not None:
        out["target"] = _numeric_target(trn, y, y_mask, task, classes)
    if with_power and trn is not None and y is not None:
        out["power"] = _power(quantile_codes(trn, 20)[0], y, y_mask, task)
    return out


def _power(codes, y, y_mask, task):
    m = y_mask if y_mask is not None else np.ones(len(y), bool)
    return oof_power(codes[m], y[m], task)


# ── 숫자형 분포
def _numeric_dist(trn, ten, n_bins: int = 40, datetime: bool = False) -> dict | None:
    parts = [a[np.isfinite(a)] for a in (trn, ten) if a is not None]
    allv = np.concatenate(parts) if parts else np.array([])
    if allv.size == 0:
        return None
    lo, hi = np.quantile(allv, [0.005, 0.995]) if not datetime else (allv.min(), allv.max())
    if lo == hi:
        lo, hi = allv.min(), allv.max()
    if lo == hi:
        hi = lo + 1
    edges = np.linspace(lo, hi, n_bins + 1)
    clipped = bool((allv < lo).any() or (allv > hi).any())

    def hist(a):
        if a is None:
            return None
        f = a[np.isfinite(a)]
        if f.size == 0:
            return [0.0] * n_bins
        c, _ = np.histogram(np.clip(f, lo, hi), bins=edges)
        return (c / f.size).tolist()

    return {"type": "hist", "edges": edges.tolist(), "train": hist(trn), "test": hist(ten),
            "clipped": clipped, "datetime": datetime}


def _numeric_drift(trn, ten) -> dict | None:
    if trn is None or ten is None:
        return None
    a, b = trn[np.isfinite(trn)], ten[np.isfinite(ten)]
    out = {"missing_train": float(1 - a.size / max(len(trn), 1)),
           "missing_test": float(1 - b.size / max(len(ten), 1))}
    if a.size < 2 or b.size < 2:
        out.update({"psi": None, "ks": None, "level": "unknown"})
        return out
    edges = np.unique(np.quantile(a, np.linspace(0, 1, 11)[1:-1]))
    pa = np.bincount(np.searchsorted(edges, a, side="right"), minlength=len(edges) + 1) / a.size
    pb = np.bincount(np.searchsorted(edges, b, side="right"), minlength=len(edges) + 1) / b.size
    # 결측 비율 차이도 분포 차이의 일부로 본다
    pa = np.append(pa * (1 - out["missing_train"]), out["missing_train"])
    pb = np.append(pb * (1 - out["missing_test"]), out["missing_test"])
    p = psi(pa, pb)
    ia, ib = sample_index(a.size, 200_000, 1), sample_index(b.size, 200_000, 2)
    ks = stats.ks_2samp(a[ia], b[ib])
    out.update({
        "psi": p, "ks": float(ks.statistic), "ks_p": float(ks.pvalue),
        "mean_shift": float((b.mean() - a.mean()) / (a.std() + 1e-12)),
        "test_out_of_range": float(((b < a.min()) | (b > a.max())).mean()),
        "level": drift_level(p),
    })
    return out


def _numeric_target(trn, y, y_mask, task, classes, n_bins: int = 10, datetime: bool = False) -> dict | None:
    m = y_mask if y_mask is not None else np.ones(len(y), bool)
    x, yy = trn[m], y[m]
    codes, edges = quantile_codes(x, n_bins)
    labels = []
    lo = np.nanmin(x) if np.isfinite(x).any() else 0.0
    bounds = [lo] + list(edges) + [np.nanmax(x) if np.isfinite(x).any() else 0.0]
    for i in range(len(edges) + 1):
        labels.append([float(bounds[i]), float(bounds[i + 1])])
    return _group_target(codes, len(edges) + 2, yy, task, classes,
                         labels=[("range", lb) for lb in labels] + [("missing", None)], datetime=datetime)


# ── 범주형 분포
def _categorical_dist(tr, te, numeric_order: bool = False) -> dict:
    vc_tr = tr.value_counts(dropna=False) if tr is not None else pd.Series(dtype="int64")
    vc_te = te.value_counts(dropna=False) if te is not None else pd.Series(dtype="int64")
    n_tr, n_te = (len(tr) if tr is not None else 0), (len(te) if te is not None else 0)
    total = vc_tr.add(vc_te, fill_value=0).sort_values(ascending=False)
    keys = list(total.index[:TOP_K])
    if numeric_order:
        keys = sorted(keys, key=lambda k: (pd.isna(k), k if not pd.isna(k) else 0))
    cats, a, b = [], [], []
    for k in keys:
        cats.append(as_label(k))
        a.append(float(vc_tr.get(k, 0) / n_tr) if n_tr else None)
        b.append(float(vc_te.get(k, 0) / n_te) if n_te else None)
    rest = total.index[TOP_K:]
    if len(rest):
        cats.append(f"(기타 {len(rest)}개)")
        a.append(float(vc_tr.reindex(rest).fillna(0).sum() / n_tr) if n_tr else None)
        b.append(float(vc_te.reindex(rest).fillna(0).sum() / n_te) if n_te else None)
    return {"type": "bar", "categories": cats,
            "train": a if tr is not None else None, "test": b if te is not None else None,
            "n_categories": int(total.size)}


def _categorical_drift(tr, te) -> dict | None:
    if tr is None or te is None:
        return None
    vc_tr = tr.value_counts(dropna=False)
    vc_te = te.value_counts(dropna=False)
    keys = vc_tr.index.union(vc_te.index)
    pa = vc_tr.reindex(keys).fillna(0).to_numpy(dtype=float)
    pb = vc_te.reindex(keys).fillna(0).to_numpy(dtype=float)
    # 범주가 아주 많으면 상위 50개 + 나머지로 묶어 PSI가 범주 수 때문에 부풀지 않게
    if len(keys) > 50:
        order = np.argsort(-(pa + pb))
        top, rest = order[:50], order[50:]
        pa = np.append(pa[top], pa[rest].sum())
        pb = np.append(pb[top], pb[rest].sum())
    pa, pb = pa / max(pa.sum(), 1), pb / max(pb.sum(), 1)
    seen = set(tr.dropna().unique().tolist())
    te_nn = te.dropna()
    unseen_mask = ~te_nn.isin(seen)
    p = psi(pa, pb)
    unseen_rate = float(unseen_mask.sum() / max(len(te), 1))
    level, basis = drift_level(p), "psi"
    if len(keys) > 50:
        # 고유값이 아주 많으면 PSI가 표본 잡음으로 부풀어서, test에 처음 보는 값의 비율로 판정한다.
        level = "shift" if unseen_rate >= 0.3 else "watch" if unseen_rate >= 0.05 else "stable"
        basis = "unseen"
    return {
        "psi": p, "level": level, "level_basis": basis,
        "missing_train": float(tr.isna().mean()), "missing_test": float(te.isna().mean()),
        "unseen_categories": int(te_nn[unseen_mask].nunique()),
        "unseen_rate": unseen_rate,
        "train_only_categories": int(len(seen - set(te_nn.unique().tolist()))),
    }


def _categorical_target(tr, y, y_mask, task, classes) -> dict | None:
    m = y_mask if y_mask is not None else np.ones(len(y), bool)
    s = tr[m] if isinstance(tr, pd.Series) else tr
    s = s.reset_index(drop=True)
    vc = s.value_counts(dropna=False)
    keys = list(vc.index[:TOP_K])
    lookup = {as_label(k): i for i, k in enumerate(keys)}
    lab = s.map(as_label) if len(s) <= 2_000_000 else s.astype(str)
    codes = lab.map(lookup).fillna(len(keys)).astype(np.int64).to_numpy()
    labels = [("category", as_label(k)) for k in keys] + [("other", f"(기타 {max(vc.size - len(keys), 0)}개)")]
    return _group_target(codes, len(keys) + 1, y[m], task, classes, labels=labels)


def _group_target(codes, n_groups, y, task, classes, labels, datetime: bool = False) -> dict:
    cnt = np.bincount(codes, minlength=n_groups)[:n_groups]
    groups = []
    if task == "multiclass":
        k_top = min(len(classes or []), 8) or int(y.max()) + 1
        overall = np.bincount(y.astype(np.int64), minlength=k_top) / max(len(y), 1)
        top_classes = np.argsort(overall)[::-1][:k_top]
        for g in range(n_groups):
            if cnt[g] == 0:
                continue
            sel = codes == g
            dist = np.bincount(y[sel].astype(np.int64), minlength=len(overall)) / cnt[g]
            groups.append({"label": labels[g][1], "label_type": labels[g][0], "count": int(cnt[g]),
                           "rates": [float(dist[k]) for k in top_classes]})
        return {"task": task, "groups": groups, "datetime": datetime,
                "classes": [str(classes[k]) if classes and k < len(classes) else str(k) for k in top_classes],
                "overall": [float(overall[k]) for k in top_classes]}
    s = np.bincount(codes, weights=y, minlength=n_groups)[:n_groups]
    s2 = np.bincount(codes, weights=y * y, minlength=n_groups)[:n_groups]
    for g in range(n_groups):
        if cnt[g] == 0:
            continue
        mean = s[g] / cnt[g]
        var = max(s2[g] / cnt[g] - mean * mean, 0.0)
        groups.append({"label": labels[g][1], "label_type": labels[g][0], "count": int(cnt[g]),
                       "mean": float(mean), "std": float(np.sqrt(var))})
    return {"task": task, "groups": groups, "overall": float(y.mean()) if len(y) else None,
            "datetime": datetime,
            "positive_class": str(classes[1]) if task == "binary" and classes and len(classes) > 1 else None}
