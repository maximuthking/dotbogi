"""데이터 점검: 대회에서 자주 터지는 문제를 찾아 중요도 순 목록으로 돌려준다.

각 항목: {id, level(danger|warn|info|ok), title, detail, columns, action}
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schema import to_datetime_safe
from ..utils import as_label, to_float
from .common import auc_score, feature_codes, oof_power, quantile_codes

LEVEL_ORDER = {"danger": 0, "warn": 1, "info": 2, "ok": 3}


def _item(cid, level, title, detail, columns=None, action=None, data=None):
    return {"id": cid, "level": level, "title": title, "detail": detail,
            "columns": list(columns or []), "action": action, "data": data}


def run_checks(train: pd.DataFrame, test: pd.DataFrame | None, sample_sub: pd.DataFrame | None,
               columns: list, target: list[str], id_col: str | None, task: str,
               y: np.ndarray | None, y_mask: np.ndarray | None, profiles: dict | None = None,
               progress=None) -> list[dict]:
    """profiles: {컬럼명: profile_column 결과} 가 있으면 다시 계산하지 않고 재사용."""
    items: list[dict] = []
    info = {c.name: c for c in columns}
    feats = [c for c in columns if c.name not in target and c.name != id_col]
    profiles = profiles or {}

    def step(frac, msg):
        if progress:
            progress(frac, msg)

    step(0.05, "중복 행 확인")
    items += _check_duplicates(train, test, feats, target)
    step(0.25, "train-test 겹침 확인")
    items += _check_overlap(train, test, feats, target, task)
    step(0.4, "컬럼 구성 확인")
    items += _check_column_sets(train, test, target, id_col)
    items += _check_sample_sub(test, sample_sub, id_col)
    step(0.5, "결측·상수 컬럼 확인")
    items += _check_missing_constant(train, test, feats)
    items += _check_dirty_values(train, test, feats)
    if y is not None:
        step(0.6, "타깃 확인")
        items += _check_target(train, target, task, y, y_mask)
        step(0.7, "누수 의심 컬럼 확인")
        items += _check_leaks(train, feats, id_col, info, task, y, y_mask, profiles)
    step(0.8, "그룹 구조 확인")
    groups = find_group_candidates(train, test, feats)
    items += _check_groups(groups)
    step(0.85, "분포 차이 확인")
    group_names = {g["column"] for g in groups}
    items += _check_drift([c for c in feats if c.name not in group_names], profiles)
    step(0.9, "시간 구조 확인")
    items += _check_time(train, test, feats)
    step(0.95, "비슷한 컬럼 확인")
    items += _check_correlated(train, feats)

    items.sort(key=lambda it: LEVEL_ORDER[it["level"]])
    return items


# ─────────────────────────────────────────────────────────── 개별 점검
def _check_duplicates(train, test, feats, target):
    out = []
    names = [c.name for c in feats if c.in_train]
    if not names:
        return out
    full_dup = int(train.duplicated().sum())
    if full_dup:
        out.append(_item("dup_rows", "warn", f"train에 완전히 같은 행이 {full_dup:,}개 있습니다",
                         f"전체의 {full_dup / len(train):.2%}입니다. K-Fold에서 같은 행이 학습·검증에 나뉘면 "
                         "검증 점수가 부풀려질 수 있습니다.",
                         action="중복을 지우거나, 같은 행이 한 폴드에만 들어가도록 그룹 K-Fold를 쓰세요."))
    if target:
        key = train[names]
        dup_mask = key.duplicated(keep=False)
        if dup_mask.any():
            grp = train.loc[dup_mask, names + target[:1]]
            conflicts = grp.groupby(names, dropna=False, sort=False)[target[0]].nunique(dropna=False)
            n_conf = int((conflicts > 1).sum())
            if n_conf:
                out.append(_item("dup_conflict", "info",
                                 f"입력은 같은데 타깃이 다른 행 묶음이 {n_conf:,}개 있습니다",
                                 "같은 입력에 다른 정답이 있다는 뜻이라 어떤 모델도 이 행들을 완벽히 맞출 수 없습니다. "
                                 "노이즈나 빠진 정보(시간, 사람 등)가 있는지 확인해 보세요.", columns=target[:1]))
    return out


def _row_hash(df: pd.DataFrame) -> np.ndarray:
    return pd.util.hash_pandas_object(df.astype("string").fillna("<NA>"), index=False).to_numpy()


def _check_overlap(train, test, feats, target, task):
    out = []
    if test is None:
        return out
    names = [c.name for c in feats if c.in_train and c.in_test]
    if not names:
        return out
    h_tr = _row_hash(train[names])
    h_te = _row_hash(test[names])
    in_train = np.isin(h_te, h_tr)
    n = int(in_train.sum())
    if n == 0:
        out.append(_item("overlap", "ok", "test 행 중 train과 똑같은 행은 없습니다",
                         "입력값이 완전히 같은 행이 train과 test 사이에 없습니다."))
        return out
    share = n / len(test)
    level = "danger" if share > 0.05 else "warn"
    detail = (f"test {len(test):,}행 중 {n:,}행({share:.2%})이 train의 어떤 행과 입력값이 완전히 같습니다.")
    if target and task != "regression":
        detail += " 이 행들은 train의 정답을 그대로 가져다 쓰면 거의 맞을 가능성이 있습니다(대회 규칙을 확인하세요)."
    out.append(_item("overlap", level, f"test 행의 {share:.1%}가 train에 그대로 있습니다", detail,
                     action="검증 점수가 리더보드와 다르게 나올 수 있으니, 겹치는 행만 따로 점수를 확인해 보세요.",
                     data={"n_overlap": n, "share": share}))
    return out


def _check_column_sets(train, test, target, id_col):
    out = []
    if test is None:
        out.append(_item("no_test", "info", "test 파일이 없습니다",
                         "train만 있어서 train/test 비교와 제출 점검은 할 수 없습니다."))
        return out
    only_train = [c for c in train.columns if c not in test.columns and c not in target]
    only_test = [c for c in test.columns if c not in train.columns]
    if only_train:
        out.append(_item("only_train", "warn", f"train에만 있는 컬럼이 {len(only_train)}개 있습니다",
                         "타깃이 아닌데 test에 없는 컬럼입니다. 예측할 때는 쓸 수 없으니 학습에서 빼야 합니다. "
                         "단, 보조 타깃이나 학습용 힌트로는 쓸 수 있습니다.", columns=only_train,
                         action="모델 입력에서 빼세요."))
    if only_test:
        out.append(_item("only_test", "warn", f"test에만 있는 컬럼이 {len(only_test)}개 있습니다",
                         "train에 없는 컬럼은 학습에 쓸 수 없습니다. 이름이 조금 다른 같은 컬럼인지 확인하세요.",
                         columns=only_test))
    return out


def _check_sample_sub(test, sample_sub, id_col):
    out = []
    if sample_sub is None or test is None:
        return out
    if len(sample_sub) != len(test):
        out.append(_item("sub_rows", "warn", "sample_submission과 test의 행 수가 다릅니다",
                         f"test {len(test):,}행, sample_submission {len(sample_sub):,}행입니다. "
                         "제출 파일은 sample_submission 기준으로 만들어야 합니다."))
    elif id_col and id_col in sample_sub.columns and id_col in test.columns:
        same_order = bool((sample_sub[id_col].astype(str).to_numpy() == test[id_col].astype(str).to_numpy()).all())
        if not same_order:
            out.append(_item("sub_order", "warn", "sample_submission의 ID 순서가 test와 다릅니다",
                             "test 순서대로 예측값을 붙이면 엉뚱한 행에 들어갑니다. ID로 합쳐서(merge) 제출 파일을 만드세요.",
                             columns=[id_col]))
    return out


def _check_missing_constant(train, test, feats):
    out = []
    high_missing, const, near_const, miss_gap = [], [], [], []
    for c in feats:
        if c.kind == "constant":
            const.append(c.name)
            continue
        s = train[c.name] if c.in_train else None
        if s is not None:
            mr = float(s.isna().mean())
            if mr > 0.5:
                high_missing.append((c.name, mr))
            vc = s.value_counts(dropna=False, normalize=True)
            if len(vc) and vc.iloc[0] > 0.995:
                near_const.append(c.name)
            if test is not None and c.in_test:
                mt = float(test[c.name].isna().mean())
                if abs(mt - mr) > 0.1:
                    miss_gap.append((c.name, mr, mt))
    if const:
        out.append(_item("constant", "info", f"값이 하나뿐인 컬럼이 {len(const)}개 있습니다",
                         "모델에 아무 정보도 주지 않습니다.", columns=const, action="빼도 됩니다."))
    if near_const:
        out.append(_item("near_constant", "info", f"99.5% 이상이 같은 값인 컬럼이 {len(near_const)}개 있습니다",
                         "거의 정보가 없지만, 드문 값이 타깃과 강하게 관련된 경우도 있으니 확인 후 빼세요.",
                         columns=near_const))
    if high_missing:
        names = [n for n, _ in sorted(high_missing, key=lambda t: -t[1])]
        out.append(_item("high_missing", "info", f"절반 이상이 비어 있는 컬럼이 {len(high_missing)}개 있습니다",
                         "트리 모델은 결측을 그대로 다룰 수 있습니다. '결측 여부' 자체가 정보가 되는지 타깃 관계를 보세요.",
                         columns=names))
    if miss_gap:
        detail = ", ".join(f"{n} (train {a:.0%} → test {b:.0%})" for n, a, b in miss_gap[:6])
        out.append(_item("missing_gap", "warn", f"train과 test의 결측 비율이 크게 다른 컬럼이 {len(miss_gap)}개 있습니다",
                         detail + ". 수집 방식이 바뀌었을 수 있고, 결측 여부를 쓰는 모델은 test에서 다르게 동작합니다.",
                         columns=[n for n, _, _ in miss_gap]))
    return out


def _check_dirty_values(train, test, feats):
    """숫자인데 문자로 저장된 컬럼, 앞뒤 공백·대소문자만 다른 범주."""
    out = []
    numeric_like, spacing = [], []
    for c in feats:
        if c.kind not in ("categorical", "binary") or not c.in_train:
            continue
        s = train[c.name].dropna()
        if s.empty or pd.api.types.is_numeric_dtype(s):
            continue
        sample = s.sample(min(len(s), 5000), random_state=0).astype(str)
        parsed = pd.to_numeric(sample.str.replace(",", "", regex=False), errors="coerce")
        rate = float(parsed.notna().mean())
        if 0.9 <= rate < 1.0 or (rate == 1.0 and c.n_unique > 30):
            bad = sample[parsed.isna()].unique()[:3].tolist()
            numeric_like.append((c.name, rate, bad))
        uniq = pd.Series(s.unique()).astype(str)
        if len(uniq) <= 5000:
            norm = uniq.str.strip().str.lower()
            if norm.nunique() < len(uniq):
                spacing.append(c.name)
    if numeric_like:
        detail = "; ".join(f"{n}: {r:.0%}가 숫자" + (f" (숫자 아닌 값 예: {', '.join(map(repr, b))})" if b else "")
                           for n, r, b in numeric_like[:5])
        out.append(_item("numeric_as_text", "warn", f"숫자인데 문자로 저장된 것 같은 컬럼이 {len(numeric_like)}개 있습니다",
                         detail + ". 숫자로 바꾸면 모델이 크기 순서를 쓸 수 있습니다.",
                         columns=[n for n, _, _ in numeric_like],
                         action="숫자가 아닌 값을 정리한 뒤 pd.to_numeric으로 바꾸세요."))
    if spacing:
        out.append(_item("dirty_categories", "warn", f"앞뒤 공백이나 대소문자만 다른 범주가 있는 컬럼이 {len(spacing)}개 있습니다",
                         "예: 'Male'과 'male '이 다른 값으로 취급됩니다.", columns=spacing,
                         action="str.strip().str.lower() 등으로 정리하세요."))
    return out


def _check_target(train, target, task, y, y_mask):
    out = []
    t = target[0] if target else None
    if t is None:
        return out
    miss = int((~y_mask).sum()) if y_mask is not None else 0
    if miss:
        out.append(_item("target_missing", "warn", f"타깃이 비어 있는 train 행이 {miss:,}개 있습니다",
                         "학습할 때 빼야 합니다. 일부러 비워 둔 준지도 학습용 데이터일 수도 있습니다.", columns=[t]))
    yy = y[y_mask] if y_mask is not None else y
    if task == "binary" and len(yy):
        pos = float(yy.mean())
        minority = min(pos, 1 - pos)
        if minority < 0.05:
            out.append(_item("imbalance", "warn", f"타깃이 크게 불균형합니다 (적은 쪽 {minority:.2%})",
                             "정확도(accuracy)는 의미가 없고 AUC·F1·PR-AUC 같은 지표를 봐야 합니다. "
                             "K-Fold는 층화(Stratified)로 나누세요.", columns=[t]))
        elif minority < 0.2:
            out.append(_item("imbalance", "info", f"타깃이 다소 불균형합니다 (적은 쪽 {minority:.1%})",
                             "층화 K-Fold로 폴드마다 비율을 맞추세요.", columns=[t]))
    elif task == "multiclass" and len(yy):
        counts = np.bincount(yy.astype(np.int64))
        counts = counts[counts > 0]
        rare = int((counts < 10).sum())
        if rare:
            out.append(_item("rare_class", "warn", f"10개 미만인 클래스가 {rare}개 있습니다",
                             "K-Fold에서 어떤 폴드에는 이 클래스가 없을 수 있습니다. 층화 K-Fold를 쓰고 폴드 수를 줄여 보세요.",
                             columns=[t]))
    elif task == "regression" and len(yy) > 2:
        from scipy import stats as st
        sk = float(st.skew(yy[:500_000]))
        if abs(sk) > 2 and yy.min() >= 0:
            out.append(_item("target_skew", "info", f"타깃 분포가 한쪽으로 크게 치우쳐 있습니다 (왜도 {sk:.1f})",
                             "log1p로 바꿔 학습하고 예측 후 expm1로 되돌리면 RMSE/RMSLE가 좋아지는 경우가 많습니다.",
                             columns=[t]))
    return out


def _check_leaks(train, feats, id_col, info, task, y, y_mask, profiles):
    out = []
    m = y_mask if y_mask is not None else np.ones(len(y), bool)
    yy = y[m]
    thresh = {"auc": 0.97, "macro_auc": 0.97, "r2": 0.9}
    suspects = []
    for c in feats:
        if not c.in_train or c.kind in ("constant",):
            continue
        p = (profiles.get(c.name) or {}).get("power")
        if p is None:
            codes = feature_codes(train[c.name], c.kind)
            p = oof_power(codes[m], yy, task)
        if p.get("metric") and p.get("value") is not None and p["value"] >= thresh[p["metric"]]:
            suspects.append((c.name, p["metric"], p["value"]))
    if suspects:
        detail = ", ".join(f"{n} ({mt.upper()} {v:.3f})" for n, mt, v in suspects[:6])
        out.append(_item("leak_suspect", "danger", f"컬럼 하나만으로 타깃이 거의 맞춰지는 컬럼이 {len(suspects)}개 있습니다",
                         detail + ". 정답에서 만들어진 컬럼(누수)이거나 매우 강한 피처입니다. test에도 같은 의미로 있는지 꼭 확인하세요.",
                         columns=[n for n, _, _ in suspects],
                         action="test에서 같은 방식으로 얻을 수 없는 값이면 학습에서 빼세요."))

    # 행 순서·ID에 타깃 정보가 있는지
    order_scores = {}
    order_codes = quantile_codes(np.arange(len(train), dtype="float64"), 20)[0]
    order_scores["행 순서"] = oof_power(order_codes[m], yy, task)
    if id_col and id_col in train.columns:
        idv = to_float(train[id_col]) if pd.api.types.is_numeric_dtype(train[id_col]) else None
        if idv is not None and np.isfinite(idv).any():
            order_scores[f"ID({id_col})"] = oof_power(quantile_codes(idv, 20)[0][m], yy, task)
    leaky = {k: v for k, v in order_scores.items() if v.get("power") is not None and v["power"] > 0.1}
    if leaky:
        detail = ", ".join(f"{k}: {v['metric'].upper()} {v['value']:.3f}" for k, v in leaky.items())
        out.append(_item("order_leak", "warn", "행 순서나 ID만으로 타깃이 어느 정도 맞춰집니다",
                         detail + ". 데이터가 타깃이나 시간 순으로 정렬돼 있을 수 있습니다. "
                         "섞지 않은 K-Fold(shuffle=False)는 위험하고, ID를 피처로 쓰면 test에서 다르게 동작할 수 있습니다.",
                         columns=[id_col] if id_col else [],
                         action="K-Fold에 shuffle=True를 쓰고, 시간 순서라면 시간 기준 검증을 고려하세요."))
    return out


def _check_drift(feats, profiles):
    out = []
    shifted, unseen = [], []
    for c in feats:
        d = (profiles.get(c.name) or {}).get("drift")
        if not d:
            continue
        high_card = c.n_unique > 50 and c.kind in ("categorical", "text")
        if not high_card and d.get("level") == "shift" and c.kind != "datetime":
            shifted.append((c.name, d.get("psi") or 0))
        if c.kind != "text" and d.get("unseen_rate") is not None and d["unseen_rate"] > 0.01:
            unseen.append((c.name, d["unseen_rate"], d.get("unseen_categories", 0)))
    if shifted:
        shifted.sort(key=lambda t: -t[1])
        out.append(_item("drift", "warn", f"train과 test 분포가 크게 다른 컬럼이 {len(shifted)}개 있습니다",
                         ", ".join(f"{n} (PSI {p:.2f})" for n, p in shifted[:6]) +
                         ". 이 컬럼에 크게 의존하는 모델은 리더보드에서 점수가 떨어질 수 있습니다.",
                         columns=[n for n, _ in shifted],
                         action="'train vs test' 화면에서 분포를 비교하고, 적대적 검증으로 영향이 큰지 확인하세요."))
    if unseen:
        unseen.sort(key=lambda t: -t[1])
        out.append(_item("unseen", "warn", f"test에 train에 없던 범주가 나오는 컬럼이 {len(unseen)}개 있습니다",
                         ", ".join(f"{n} (test 행의 {r:.1%}, 새 범주 {k:,}개)" for n, r, k in unseen[:6]) +
                         ". 모델은 처음 보는 범주를 결측처럼 다룹니다.",
                         columns=[n for n, _, _ in unseen],
                         action="드문 범주를 '기타'로 묶거나 빈도 인코딩을 써 보세요."))
    return out


def _check_time(train, test, feats):
    out = []
    for c in feats:
        if c.kind != "datetime" or not c.in_train:
            continue
        a = to_datetime_safe(train[c.name]).dropna()
        if a.empty:
            continue
        if test is None or not c.in_test:
            out.append(_item("time_col", "info", f"날짜 컬럼 '{c.name}'이 있습니다",
                             f"train 기간: {a.min():%Y-%m-%d} ~ {a.max():%Y-%m-%d}", columns=[c.name]))
            continue
        b = to_datetime_safe(test[c.name]).dropna()
        if b.empty:
            continue
        a_min, a_max, b_min, b_max = a.min(), a.max(), b.min(), b.max()
        rng = f"train {a_min:%Y-%m-%d} ~ {a_max:%Y-%m-%d}, test {b_min:%Y-%m-%d} ~ {b_max:%Y-%m-%d}"
        if b_min >= a_max:
            gap = (b_min - a_max).days
            out.append(_item("time_split", "warn", f"test 기간이 train 이후입니다 ('{c.name}')",
                             rng + (f" (사이 {gap}일)" if gap > 1 else "") +
                             ". 미래를 예측하는 대회입니다. 무작위 K-Fold는 미래 정보를 섞어 점수가 낙관적으로 나옵니다.",
                             columns=[c.name], action="시간 기준 검증(마지막 기간을 검증으로)을 쓰세요.",
                             data={"split": "after", "gap_days": gap}))
        elif b_max <= a_min:
            out.append(_item("time_split", "warn", f"test 기간이 train 이전입니다 ('{c.name}')", rng,
                             columns=[c.name], action="시간 기준 검증을 고려하세요.", data={"split": "before"}))
        else:
            overlap = float(((b >= a_min) & (b <= a_max)).mean())
            out.append(_item("time_split", "info", f"train과 test 기간이 겹칩니다 ('{c.name}')",
                             rng + f". test의 {overlap:.0%}가 train 기간 안에 있습니다. 무작위 K-Fold를 써도 괜찮은 편입니다.",
                             columns=[c.name], data={"split": "overlap", "overlap": overlap}))
    return out


def find_group_candidates(train, test, feats) -> list[dict]:
    """같은 값이 여러 행에 반복되고, test 값이 train과 대부분 겹치지 않는 컬럼 → 그룹 K-Fold 후보."""
    cands = []
    if test is None:
        return cands
    for c in feats:
        if not (c.in_train and c.in_test) or c.kind in ("constant", "text", "binary", "datetime"):
            continue
        if c.kind == "numeric" and not pd.api.types.is_integer_dtype(train[c.name]):
            continue
        a = train[c.name].dropna()
        nu = a.nunique()
        if nu < 10 or nu > len(a) / 2:
            continue
        b = test[c.name].dropna()
        unseen = float((~b.isin(set(a.unique().tolist()))).mean()) if len(b) else 0.0
        if unseen >= 0.5:
            cands.append({"column": c.name, "n_groups": int(nu), "rows_per_group": len(a) / nu,
                          "test_unseen_rate": unseen})
    cands.sort(key=lambda d: -d["test_unseen_rate"])
    return cands


def _check_groups(cands):
    if not cands:
        return []
    detail = ", ".join(f"{d['column']} (그룹 {d['n_groups']:,}개, 그룹당 {d['rows_per_group']:.1f}행, "
                       f"test 값의 {d['test_unseen_rate']:.0%}가 train에 없음)" for d in cands[:4])
    return [_item("groups", "warn", "test가 train과 다른 그룹으로 이뤄진 것 같습니다",
                  detail + ". 같은 그룹이 학습·검증에 나뉘면 검증 점수가 리더보드보다 좋게 나옵니다.",
                  columns=[d["column"] for d in cands],
                  action=f"'{cands[0]['column']}' 기준 그룹 K-Fold를 쓰세요.", data={"candidates": cands})]


def _check_correlated(train, feats, threshold: float = 0.98):
    names = [c.name for c in feats if c.in_train and c.kind == "numeric"]
    if len(names) < 2:
        return []
    names = names[:300]
    sample = train[names].sample(min(len(train), 50_000), random_state=0)
    corr = sample.apply(lambda s: pd.to_numeric(s, errors="coerce")).corr().abs()
    pairs = []
    vals = corr.to_numpy()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if vals[i, j] >= threshold:
                pairs.append((names[i], names[j], float(vals[i, j])))
    if not pairs:
        return []
    pairs.sort(key=lambda t: -t[2])
    return [_item("correlated", "info", f"거의 같은 정보를 가진 컬럼 쌍이 {len(pairs)}개 있습니다",
                  ", ".join(f"{a} ~ {b} (r={r:.3f})" for a, b, r in pairs[:5]) +
                  ". 트리 모델에는 큰 문제가 없지만, 중요도가 둘로 나뉘어 보이고 선형 모델에는 해가 될 수 있습니다.",
                  columns=sorted({p for a, b, _ in pairs for p in (a, b)}))]
