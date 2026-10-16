"""제출 파일 검사: sample_submission과 형식 비교, 값 범위·결측 확인, 안전한 자동 수정, 두 제출물 비교."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M


def _item(level, title, detail="", fixable=False):
    return {"level": level, "title": title, "detail": detail, "fixable": fixable}


def _key(s: pd.Series) -> pd.Series:
    """ID 비교용 문자열 (1.0과 1을 같게)."""
    if pd.api.types.is_float_dtype(s):
        v = s.to_numpy()
        if np.all(np.isnan(v) | (np.mod(v, 1) == 0)):
            return s.astype("Int64").astype("string")
    return s.astype("string").str.strip()


def check_submission(sub: pd.DataFrame, sample: pd.DataFrame | None, id_col: str | None = None,
                     task: str | None = None, metric: str | None = None, classes: list | None = None,
                     submission_format: str = "value", y_train: pd.Series | None = None) -> dict:
    items: list[dict] = []
    pred_cols: list[str] = []

    unnamed = [c for c in sub.columns if str(c).startswith("Unnamed")]
    if unnamed:
        items.append(_item("danger", "인덱스 컬럼이 같이 저장됐습니다",
                           f"{unnamed} 컬럼이 있습니다. to_csv(index=False)로 저장하세요.", fixable=True))

    if sample is not None:
        exp_cols = list(sample.columns)
        got = [c for c in sub.columns if c not in unnamed]
        missing = [c for c in exp_cols if c not in got]
        extra = [c for c in got if c not in exp_cols]
        if missing:
            items.append(_item("danger", f"필요한 컬럼이 없습니다: {missing}",
                               "컬럼 이름은 대소문자·공백까지 sample_submission과 같아야 합니다."))
        if extra:
            items.append(_item("warn", f"sample_submission에 없는 컬럼이 있습니다: {extra}",
                               "대부분의 대회에서 오류가 나거나 무시됩니다.", fixable=True))
        if not missing and [c for c in got if c in exp_cols] != exp_cols:
            items.append(_item("warn", "컬럼 순서가 sample_submission과 다릅니다",
                               "이름으로 읽는 대회가 많지만 순서로 읽는 곳도 있어 맞춰 두는 게 안전합니다.", fixable=True))
        if len(sub) != len(sample):
            items.append(_item("danger", f"행 수가 다릅니다 (제출 {len(sub):,}행, 필요 {len(sample):,}행)"))
        if id_col is None:
            id_col = exp_cols[0] if exp_cols and exp_cols[0] in sub.columns and len(exp_cols) > 1 else None
        pred_cols = [c for c in exp_cols if c != id_col and c in sub.columns]
    else:
        pred_cols = [c for c in sub.columns if c != id_col and c not in unnamed]

    # ID 점검
    if id_col and id_col in sub.columns:
        ids = _key(sub[id_col])
        dup = int(ids.duplicated().sum())
        if dup:
            items.append(_item("danger", f"중복된 ID가 {dup:,}개 있습니다"))
        if ids.isna().any():
            items.append(_item("danger", f"비어 있는 ID가 {int(ids.isna().sum()):,}개 있습니다"))
        if sample is not None and id_col in sample.columns:
            exp_ids = _key(sample[id_col])
            s_exp, s_got = set(exp_ids.dropna()), set(ids.dropna())
            miss_ids, extra_ids = s_exp - s_got, s_got - s_exp
            if miss_ids:
                ex = ", ".join(list(map(str, list(miss_ids)[:3])))
                items.append(_item("danger", f"빠진 ID가 {len(miss_ids):,}개 있습니다", f"예: {ex}"))
            if extra_ids:
                ex = ", ".join(list(map(str, list(extra_ids)[:3])))
                hint = ""
                if miss_ids and any(e.lstrip("0") in {m.lstrip("0") for m in miss_ids} for e in list(extra_ids)[:50]):
                    hint = " 앞자리 0이 사라진 것 같습니다(예: '0012' → 12). ID를 문자열로 읽으세요."
                items.append(_item("danger", f"sample_submission에 없는 ID가 {len(extra_ids):,}개 있습니다",
                                   f"예: {ex}.{hint}"))
            if not miss_ids and not extra_ids and not dup and len(ids) == len(exp_ids) \
                    and not (ids.to_numpy() == exp_ids.to_numpy()).all():
                items.append(_item("info", "ID 순서가 sample_submission과 다릅니다",
                                   "ID로 맞추는 대회라면 괜찮지만, 순서대로 맞추는 곳도 있어 정렬해 두는 게 안전합니다.",
                                   fixable=True))

    # 예측값 점검
    stats = {}
    for c in pred_cols:
        s = sub[c]
        exp_dtype = sample[c].dtype if sample is not None and c in sample.columns else None
        n_nan = int(s.isna().sum())
        if n_nan:
            items.append(_item("danger", f"'{c}'에 빈 값이 {n_nan:,}개 있습니다"))
        if pd.api.types.is_numeric_dtype(s):
            v = s.to_numpy(dtype="float64", na_value=np.nan)
            n_inf = int(np.isinf(v).sum())
            if n_inf:
                items.append(_item("danger", f"'{c}'에 무한대 값이 {n_inf:,}개 있습니다"))
            fv = v[np.isfinite(v)]
            if fv.size:
                stats[c] = {"mean": float(fv.mean()), "std": float(fv.std()), "min": float(fv.min()),
                            "max": float(fv.max()), "n_unique": int(np.unique(fv[:200_000]).size)}
                if stats[c]["n_unique"] == 1:
                    items.append(_item("warn", f"'{c}'의 예측값이 전부 같습니다 ({fv[0]:g})",
                                       "모델이 제대로 학습되지 않았거나 잘못된 컬럼을 저장했을 수 있습니다."))
            if exp_dtype is not None and not pd.api.types.is_numeric_dtype(exp_dtype):
                items.append(_item("danger", f"'{c}'는 문자(라벨)여야 하는데 숫자입니다",
                                   f"sample_submission 예: {sample[c].iloc[0]!r}. 클래스 이름으로 바꿔서 내세요."))
        elif exp_dtype is not None and pd.api.types.is_numeric_dtype(exp_dtype):
            items.append(_item("danger", f"'{c}'는 숫자여야 하는데 문자가 들어 있습니다"))

    needs = M.METRICS[metric].needs if metric in M.METRICS else None
    if task == "binary" and pred_cols:
        c = pred_cols[0]
        st = stats.get(c)
        if st:
            if st["min"] < 0 or st["max"] > 1:
                if needs == "proba" or (sample is not None and pd.api.types.is_float_dtype(sample[c])):
                    items.append(_item("danger", f"'{c}' 확률이 0~1 범위를 벗어났습니다 "
                                                 f"({st['min']:.3g} ~ {st['max']:.3g})", fixable=True))
            elif st["n_unique"] <= 2 and needs == "proba":
                items.append(_item("warn", "확률 대신 0/1 라벨을 낸 것 같습니다",
                                   f"평가 지표가 {M.METRICS[metric].label}이면 확률을 내야 점수가 훨씬 좋습니다."))
            elif needs == "label" and st["n_unique"] > 2:
                items.append(_item("warn", "라벨(0/1) 대신 확률을 낸 것 같습니다",
                                   f"평가 지표가 {M.METRICS[metric].label}이면 0/1로 바꿔야 할 수 있습니다. "
                                   "대회 안내를 확인하세요."))
            if y_train is not None and st and 0 <= st["min"] and st["max"] <= 1:
                pos = float(pd.to_numeric(y_train.astype("string").map({str(classes[1]): 1, str(classes[0]): 0})
                                          if classes and len(classes) == 2 else y_train, errors="coerce").mean())
                if np.isfinite(pos) and abs(st["mean"] - pos) > 0.15:
                    items.append(_item("warn", "예측 평균이 train 양성 비율과 많이 다릅니다",
                                       f"예측 평균 {st['mean']:.3f}, train 양성 비율 {pos:.3f}. "
                                       "클래스를 반대로 넣었는지(1-p) 확인하세요."))
    if task == "binary" and pred_cols and classes and not stats.get(pred_cols[0]):
        allowed = set(map(str, classes))
        got = set(sub[pred_cols[0]].dropna().astype(str).unique())
        bad = got - allowed
        if bad:
            items.append(_item("danger", f"허용되지 않는 라벨이 있습니다: {sorted(bad)[:5]}",
                               f"허용 값: {sorted(allowed)}"))
    if task == "multiclass" and submission_format == "proba_columns" and len(pred_cols) > 1:
        P = sub[pred_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float64")
        rs = np.nansum(P, axis=1)
        off = int((np.abs(rs - 1) > 1e-3).sum())
        if off:
            items.append(_item("warn", f"확률 합이 1이 아닌 행이 {off:,}개 있습니다",
                               "행마다 확률 합을 1로 맞추세요(정규화).", fixable=True))
        if np.nanmin(P) < 0 or np.nanmax(P) > 1:
            items.append(_item("danger", "0~1 범위를 벗어난 확률이 있습니다", fixable=True))
    if task == "multiclass" and submission_format == "value" and pred_cols and classes:
        allowed = set(map(str, classes))
        got_vals = sub[pred_cols[0]].dropna()
        got_str = set(_key(got_vals).unique()) if pd.api.types.is_numeric_dtype(got_vals) else set(got_vals.astype(str).unique())
        bad = got_str - allowed
        if bad and len(bad) <= 50:
            items.append(_item("danger", f"train에 없던 클래스 값이 있습니다: {sorted(bad)[:5]}",
                               f"허용 값 예: {sorted(allowed)[:10]}"))
    if task == "regression" and pred_cols and y_train is not None:
        yt = pd.to_numeric(y_train, errors="coerce").dropna()
        for c in pred_cols:
            st = stats.get(c)
            if not st or yt.empty:
                continue
            if yt.min() >= 0 and st["min"] < 0:
                items.append(_item("warn", f"'{c}'에 음수 예측이 있습니다 (최소 {st['min']:.3g})",
                                   "train 타깃은 전부 0 이상입니다. 0으로 자르면 보통 점수가 좋아집니다.", fixable=True))
            span = yt.max() - yt.min()
            if span > 0 and (st["max"] > yt.max() + span or st["min"] < yt.min() - span):
                items.append(_item("warn", f"'{c}' 예측 범위가 train 타깃 범위를 크게 벗어납니다",
                                   f"예측 {st['min']:.3g} ~ {st['max']:.3g}, train {yt.min():.3g} ~ {yt.max():.3g}. "
                                   "log 변환을 되돌리는 걸 잊었는지 확인하세요."))

    level_order = {"danger": 0, "warn": 1, "info": 2}
    items.sort(key=lambda it: level_order[it["level"]])
    ok = not any(it["level"] == "danger" for it in items)
    if not items:
        items.append({"level": "ok", "title": "형식 문제가 없습니다",
                      "detail": "컬럼, 행 수, ID, 값 범위가 모두 정상입니다.", "fixable": False})
    return {"ok": ok, "items": items, "stats": stats, "pred_cols": pred_cols, "id_col": id_col,
            "rows": len(sub), "fixable": any(it.get("fixable") for it in items)}


def fix_submission(sub: pd.DataFrame, sample: pd.DataFrame, id_col: str | None, task: str | None,
                   submission_format: str = "value", y_train: pd.Series | None = None) -> tuple[pd.DataFrame, list[str]]:
    """의미를 바꾸지 않는 수정만: 인덱스 컬럼 삭제, 컬럼 순서, ID 순서, 확률 자르기·정규화, 음수 자르기."""
    done = []
    sub = sub.copy()
    unnamed = [c for c in sub.columns if str(c).startswith("Unnamed")]
    if unnamed:
        sub = sub.drop(columns=unnamed)
        done.append("인덱스 컬럼 삭제")
    cols = [c for c in sample.columns if c in sub.columns]
    if list(sub.columns) != cols:
        sub = sub[cols]
        done.append("컬럼 순서를 sample_submission에 맞춤")
    if id_col and id_col in sub.columns and id_col in sample.columns:
        key_sub, key_exp = _key(sub[id_col]), _key(sample[id_col])
        if set(key_sub) == set(key_exp) and not key_sub.duplicated().any() \
                and not (key_sub.to_numpy() == key_exp.to_numpy()).all():
            pos = pd.Series(np.arange(len(sub)), index=key_sub.to_numpy())
            sub = sub.iloc[pos.loc[key_exp.to_numpy()].to_numpy()].reset_index(drop=True)
            done.append("행 순서를 sample_submission ID 순서로 정렬")
        sub[id_col] = sample[id_col].to_numpy() if len(sub) == len(sample) and \
            (_key(sub[id_col]).to_numpy() == key_exp.to_numpy()).all() else sub[id_col]
    pred_cols = [c for c in cols if c != id_col]
    if task == "binary" and pred_cols and pd.api.types.is_numeric_dtype(sub[pred_cols[0]]):
        c = pred_cols[0]
        if pd.api.types.is_float_dtype(sample[c]) and (sub[c].min() < 0 or sub[c].max() > 1):
            sub[c] = sub[c].clip(0, 1)
            done.append(f"'{c}'를 0~1로 자름")
    if task == "multiclass" and submission_format == "proba_columns" and len(pred_cols) > 1:
        P = sub[pred_cols].apply(pd.to_numeric, errors="coerce").clip(lower=0)
        rs = P.sum(axis=1).replace(0, np.nan)
        sub[pred_cols] = P.div(rs, axis=0).fillna(1 / len(pred_cols))
        done.append("확률을 0 이상으로 자르고 행 합을 1로 정규화")
    if task == "regression" and y_train is not None:
        yt = pd.to_numeric(y_train, errors="coerce")
        if yt.min() >= 0:
            for c in pred_cols:
                if pd.api.types.is_numeric_dtype(sub[c]) and (sub[c] < 0).any():
                    sub[c] = sub[c].clip(lower=0)
                    done.append(f"'{c}'의 음수 예측을 0으로 자름")
    return sub, done


def compare_submissions(a: pd.DataFrame, b: pd.DataFrame, id_col: str | None, pred_cols: list[str]) -> dict:
    """두 제출물이 얼마나 다른지: 상관, 평균 절대 차이, 라벨이 바뀐 비율."""
    if id_col and id_col in a.columns and id_col in b.columns:
        m = a[[id_col] + pred_cols].assign(_k=_key(a[id_col])).merge(
            b[[id_col] + pred_cols].assign(_k=_key(b[id_col])), on="_k", suffixes=("_a", "_b"))
    else:
        m = pd.concat([a[pred_cols].add_suffix("_a"), b[pred_cols].add_suffix("_b")], axis=1)
    out = {"matched_rows": len(m), "columns": []}
    for c in pred_cols:
        x, y = m[f"{c}_a"], m[f"{c}_b"]
        row = {"column": c}
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xv, yv = x.to_numpy(float), y.to_numpy(float)
            ok = np.isfinite(xv) & np.isfinite(yv)
            row.update({"pearson": float(np.corrcoef(xv[ok], yv[ok])[0, 1]) if ok.sum() > 2 and xv[ok].std() > 0 and yv[ok].std() > 0 else None,
                        "spearman": float(pd.Series(xv[ok]).corr(pd.Series(yv[ok]), method="spearman")) if ok.sum() > 2 else None,
                        "mean_abs_diff": float(np.mean(np.abs(xv[ok] - yv[ok]))) if ok.any() else None,
                        "changed_rate": float(np.mean(xv[ok] != yv[ok])) if ok.any() else None})
        else:
            row["changed_rate"] = float((x.astype(str) != y.astype(str)).mean())
        out["columns"].append(row)
    return out
