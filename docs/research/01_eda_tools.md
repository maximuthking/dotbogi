# 자동 EDA·데이터 탐색 도구 조사 (캐글·데이콘 참가자 관점)

조사일은 2026-10-17입니다. 링크가 없는 주장은 넣지 않았고, 확인하지 못한 내용은 "(추정)" 또는 "확인 못 함"으로 표시했습니다.

## 0. 조사 방법과 한계

**직접 조회한 것**
- 버전, 날짜, 라이선스, 스타 수는 아래 API로 직접 조회했습니다.
  - PyPI JSON API (`pypi.org/pypi/<패키지>/json`)
  - GitHub API (`gh api`)
  - VS Code Marketplace API
- 이슈는 제목과 번호를 `gh`로 하나씩 열어 확인했습니다.

**한계**
- **웹 검색 한도:** 이번 작업에서 웹 검색 한도(200회, 하위 조사와 공유)를 모두 썼습니다. 더 찾으려면 후속 요청이 필요합니다.
- **Reddit:** reddit.com이 직접 접근을 막습니다. 일부 Reddit 댓글은 하위 조사가 아카이브 사본(pullpush)으로 읽었고, 그런 항목에는 "(아카이브 사본)"이라고 표시했습니다. 링크는 원문 퍼머링크입니다.
- **Kaggle Discussion·Stack Overflow:** 직접 확인한 글은 적습니다. 사용자 평가는 주로 GitHub 이슈, Hacker News, 블로그에서 가져왔습니다.
- **이슈 키워드 건수:** 본문과 이슈 템플릿(환경 정보 칸)까지 검색되므로 잡음이 큽니다. 규모 감만 보시면 됩니다.

---

## 1. 핵심 발견 7가지

**1. ydata-profiling은 이제 `fg-data-profiling`입니다.**
- 4.19.x(2026-04)에서 이름이 바뀌었고, README는 옛 패키지에 더 이상 업데이트·버그 수정이 없다고 안내합니다. [README](https://github.com/Data-Centric-AI-Community/fg-data-profiling) · [릴리스 노트](https://github.com/Data-Centric-AI-Community/fg-data-profiling/releases) · [fg-data-profiling PyPI](https://pypi.org/project/fg-data-profiling/)
- 그런데도 Kaggle 기본 이미지에는 옛 이름인 `ydata-profiling`과 `pandas-profiling`이 들어 있습니다. [kaggle_requirements.txt](https://github.com/Kaggle/docker-python/blob/main/kaggle_requirements.txt)

**2. pandas 3 지원이 갈립니다.**
- pandas 3.0.0은 2026-01-21에 나왔습니다. [pandas PyPI 이력](https://pypi.org/project/pandas/#history)
- fg-data-profiling 4.20.0은 여전히 `pandas<3.0`을 요구하고, 지원 요청 이슈 [#1860](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1860)이 열려 있습니다.
- Data Wrangler도 pandas 3에서 노트북 렌더러가 동작하지 않는다는 이슈 [#631](https://github.com/microsoft/vscode-data-wrangler/issues/631)이 열려 있습니다 (댓글 15개).
- D-Tale은 3.19.0(2026-01-27)에서 pandas 3에 대응했습니다. [CHANGES.md](https://github.com/man-group/dtale/blob/master/CHANGES.md)

**3. 지금 Colab과 Kaggle은 Python 3.13 환경입니다.**
- Colab 런타임: Python 3.13.16, pandas 2.2.3, numpy 2.1.3. [os-info.txt](https://github.com/googlecolab/backend-info/blob/main/os-info.txt) · [pip-freeze.txt](https://github.com/googlecolab/backend-info/blob/main/pip-freeze.txt)
  - 이 목록은 실제 운영 컨테이너와 다를 수 있다고 파일에 적혀 있습니다.
- Kaggle 이미지는 Colab 런타임 이미지(2026-09-17 빌드)를 바탕으로 합니다. [Dockerfile.tmpl](https://github.com/Kaggle/docker-python/blob/main/Dockerfile.tmpl)
- 그래서 `Requires-Python <3.11`인 DataPrep 최신판은 메타데이터상 이 환경에 설치할 수 없습니다. [dataprep PyPI](https://pypi.org/project/dataprep/)

**4. 사실상 유지보수가 멈춘 도구가 넷입니다.**

| 도구 | 마지막 릴리스 | 근거 |
|---|---|---|
| Lux | 2022-02 | [PyPI](https://pypi.org/project/lux-api/) |
| DataPrep | 2022-08 | [PyPI](https://pypi.org/project/dataprep/) |
| AutoViz | 2024-06 | [PyPI](https://pypi.org/project/autoviz/) |
| dabl | 2024-12 | [PyPI](https://pypi.org/project/dabl/) |

**5. train/test 비교를 기본 기능으로 가진 도구는 소수입니다.**
- 기본 기능으로 있는 것: ydata/fg-data-profiling의 `compare()`, Sweetviz의 `compare()`
- 부분 지원: DataPrep `plot_diff`
- 인터랙티브 계열(D-Tale, PyGWalker, Mito, Data Wrangler)에는 비교 기능이 없습니다. D-Tale은 README로 확인했고, 나머지는 (추정)입니다.
- 피처별 드리프트를 수치로 순위 매기는 기능은 Deepchecks·Evidently 같은 MLOps 도구 쪽에 있습니다(6절).

**6. 타깃 전용 분석이 있는 도구도 적습니다.**
- 있는 것: AutoViz `depVar`, dabl `target_col`
- 제약이 있는 것: Sweetviz는 불리언·수치형 타깃만 받습니다. ydata는 `interactions.targets` 설정뿐입니다.

**7. 공식 한국어 UI는 하나도 확인되지 않았습니다.**
- 한글 관련 버그는 여러 곳에서 확인됩니다.
  - ydata: 그림에서 CJK 글자가 깨짐 [#1876](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1876)
  - Graphic Walker(PyGWalker의 기반): 한글 컬럼명으로 계산 필드를 만들 수 없음 [#507](https://github.com/Kanaries/graphic-walker/issues/507)

---

## 2. 메타데이터 한눈에 보기 (2026-10-17 API 조회)

| 도구 | 형태 | 라이선스 | PyPI 최신 (업로드일) | GitHub ★ / 마지막 push |
|---|---|---|---|---|
| ydata-profiling → **fg-data-profiling** | 라이브러리 (HTML 리포트, 노트북 위젯) | MIT | ydata 4.18.4 (2026-04-22)에서 끝. fg 4.20.0 (2026-09-11) | 13,729 / 2026-09-11 [repo](https://github.com/Data-Centric-AI-Community/fg-data-profiling) |
| Sweetviz | 라이브러리 (HTML 리포트) | MIT | 2.3.3 (2026-04-11). 직전 2.3.1은 2023-11-29 | 3,130 / 2026-04-11 [PyPI 이력](https://pypi.org/project/sweetviz/#history) |
| D-Tale | 라이브러리 + 로컬 웹 UI (Flask) | LGPL-2.1 | 3.22.0 (2026-04-01) | 5,231 / 2026-07-24 [repo](https://github.com/man-group/dtale) |
| AutoViz | 라이브러리 (차트 묶음, HTML) | Apache-2.0 | 0.1.905 (2024-06-10) | 1,904 / 2024-06-10 [repo](https://github.com/AutoViML/AutoViz) |
| DataPrep.EDA | 라이브러리 (HTML 리포트) | MIT | 0.4.5 (2022-08-04) | 2,268 / 2024-06-27 [repo](https://github.com/sfu-db/dataprep) |
| Lux | 노트북 위젯 | Apache-2.0 | 0.5.1 (2022-02-19) | 5,381 / 2024-03-20 [repo](https://github.com/lux-org/lux) |
| PyGWalker (Graphic Walker) | 노트북 위젯 (+Streamlit 등) | Apache-2.0. Graphic Walker는 브랜딩 라이선스 추가 [LICENSE2](https://github.com/Kanaries/graphic-walker/blob/main/LICENSE2) | 0.5.0.1 (2026-04-04) | 15,988 / 2026-09-05 [repo](https://github.com/Kanaries/pygwalker) |
| Mito (mitosheet) | JupyterLab 확장 (스프레드시트) | AGPL-3.0. pro·enterprise 폴더는 별도 [LICENSE](https://github.com/mito-ds/mito/blob/dev/LICENSE) | 0.2.69 (2026-07-21) | 2,653 / 2026-07-21 [repo](https://github.com/mito-ds/mito) |
| Data Wrangler (MS) | VS Code 확장 | Microsoft 독점 라이선스 [원문](https://ms-toolsai.gallerycdn.vsassets.io/extensions/ms-toolsai/datawrangler/1.24.2/1781080568046/Microsoft.VisualStudio.Services.Content.License) | 1.24.2 (Marketplace 2026-06-10), 설치 약 236만 | 이슈 전용 저장소 610 / 2025-12-03 [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler) |
| skimpy | 라이브러리 (콘솔 표) | MIT | 0.0.21 (2026-06-04) | 516 / 2026-10-14 [repo](https://github.com/aeturrell/skimpy) |
| dabl | 라이브러리 (matplotlib 그림) | BSD-3 | 0.3.2 (2024-12-16) | 725 / 2024-12-16 [repo](https://github.com/dabl/dabl) |
| klib | 라이브러리 (그림 + 정제 함수) | MIT | 1.4.1 (2026-06-18) | 523 / 2026-09-01 [repo](https://github.com/akanz1/klib) |

---

## 3. 도구별 상세

### 3-1. ydata-profiling → fg-data-profiling

**1) 요약**
- 한 줄로 결측, 상관, 경고(Alerts), 상호작용 등이 담긴 HTML·JSON 리포트를 만듭니다. pandas와 Spark를 지원합니다. [README](https://github.com/Data-Centric-AI-Community/fg-data-profiling)
- 4.19.1에 "rename to data-profiling" PR이 들어갔고, 4.20.0에서 Python 3.14를 지원했습니다. [릴리스](https://github.com/Data-Centric-AI-Community/fg-data-profiling/releases)
- 의존성 제약: `pandas<3.0`, `numpy<2.6`, Python 3.10~3.14. [PyPI](https://pypi.org/project/fg-data-profiling/)

**2) 잘하는 점**
- Alerts 페이지(결측, 고카디널리티, 고상관, 0값), 세 가지 상관(Pearson·Spearman·Kendall), 재현 정보가 강점으로 꼽힙니다. [dataroots 비교글 (2023-06)](https://dev.to/dataroots/streamlining-data-exploration-a-comparison-of-profiling-tools-for-effective-eda-160p)
- 가장 많이 쓰이는 도구입니다. 스타 13.7k이고 Kaggle 이미지에 기본 포함돼 있습니다. [kaggle_requirements.txt](https://github.com/Kaggle/docker-python/blob/main/kaggle_requirements.txt)
- 상관·상호작용을 끄고 4,900만 행 × 86변수를 30분에 돌렸다는 사용자 댓글이 있습니다. [#743](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/743)

**3) 반복되는 불만**

(a) 대용량
- [#743 "Pandas profiling becoming too slow : un-usable"](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/743) (open): 1만 행 × 30열에 2분 이상 걸렸다는 보고입니다.
- [#1028](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1028): 1,000행 × 118열에 500초가 걸렸습니다. 메인테이너는 열 수에 따라 계산이 제곱으로 늘어난다고 답했습니다.
- [#1272](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1272): 16GB 서버에서 프로세스가 강제 종료(Killed)됐습니다.
- 공식 문서의 대안은 minimal 모드, 샘플링, `interactions.targets` 제한, Spark입니다. Spark는 일부 기능만 지원합니다. [대용량 문서](https://docs.profiling.ydata.ai/latest/features/big_data/)
- Polars 지원 요청 [#1129](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1129)는 2022년부터 open입니다.

(b) train/test 비교: **지원합니다** (3.5.0부터).
- `report.compare(other)`를 씁니다. 문서상 완전 지원은 2개 데이터셋까지이고, Spark에서는 안 됩니다. [비교 문서](https://docs.profiling.ydata.ai/latest/features/comparing_datasets/)
- 관련 버그:
  - [#1378](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1378): datetime과 str 열 비교 시 TypeError
  - [#1652](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1652): 3개 이상 비교 시 오류

(c) 타깃 분석: **전용 기능이 없습니다.**
- 라벨 열 지원 요청 [#513](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/513)은 "interactions에만 target을 지정할 수 있다"는 답과 함께 닫혔습니다.
- 타깃 그래프 요청 [#73](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/73)도 닫혔습니다.

(d) 설치·의존성
- Python 3.12 설치 실패: [#1510](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1510) (댓글 15개)
- Python 3.13 지원: [#1695](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1695) (open)
- numba 관련 오류: [#1575](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1575) (open)
- pandas 3: [#1860](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1860) (open)
- 국내 사례: 인프런 질문(2025-07)에서 Python 버전 오류로 설치하지 못했고, 강사가 Colab 사용을 권했습니다. [인프런](https://www.inflearn.com/community/questions/1639628)

(e) HTML이 무거움
- [#1579 "Report is too large for any browser to render"](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1579): 41k 행 × 약 100열에서 약 80MB HTML이 나왔습니다. 메인테이너는 정적 HTML의 한계라고 답했습니다.
- [#1794](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1794): 단일 페이지 버전을 요청했지만 거절됐습니다.

(f) Kaggle·Colab
- Kaggle에는 기본으로 설치돼 있습니다(위 링크).
- Colab 오류 이슈:
  - [#1497](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1497): "ydata-profiling not found"
  - [#1520](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1520): typing_extensions 오류
  - [#1708](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1708): IPython 9에서 `to_notebook_iframe` 오류
- Reddit에도 Colab에서 import가 실패했다는 글이 있습니다. [r/learnpython (아카이브 사본)](https://www.reddit.com/r/learnpython/comments/193o9k0/tried_to_install_ydata_profiling_on_my_colab_it/khbdt2w/)

한글
- 패키지가 그림을 그릴 때 사용자의 matplotlib 폰트 설정을 덮어써서 CJK 글자가 깨진다는 제안 이슈가 있습니다. [#1876](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1876) · [#1729](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1729)

**4) 대회용으로 빠진 것**
- 근거 있음:
  - 타깃 분석 없음 (#513)
  - 비교는 2개까지만 완전 지원 (문서)
  - pandas 3과 Polars 미지원
  - 큰 리포트는 브라우저가 감당하지 못함
- (추정): train/test 차이를 수치로 순위화하는 기능은 없고, 두 리포트를 나란히 보여 주는 수준입니다.

### 3-2. Sweetviz

**1) 요약**
- `analyze()`, `compare()`, `compare_intra()`로 자체 완결형 HTML 리포트를 만듭니다. [README](https://github.com/fbdesignpro/sweetviz)
- 2.3.1(2023-11) 이후 약 2년 반 동안 릴리스가 없다가, 2026-04에 2.3.2와 2.3.3이 나왔습니다. [PyPI 이력](https://pypi.org/project/sweetviz/#history) · [릴리스](https://github.com/fbdesignpro/sweetviz/releases)

**2) 잘하는 점**
- 개발자 본인 글이 내세우는 강점: train/test 나란히 비교, 모든 피처 위에 타깃 겹쳐 그리기, 수치·범주 연관을 한 그래프에 표시. [KDnuggets (2021-02)](https://www.kdnuggets.com/2021/02/powerful-exploratory-data-analysis-sweetviz.html)
- 리포트가 압축적이고 인터랙티브하다는 평가가 있습니다. 다만 Alerts 섹션은 없습니다. [dataroots](https://dev.to/dataroots/streamlining-data-exploration-a-comparison-of-profiling-tools-for-effective-eda-160p)
- 일본 블로그도 학습·테스트 데이터를 타깃과 함께 비교하는 점을 Sweetviz 고유의 장점으로 꼽았습니다. [zenn (2023-06)](https://zenn.dev/satsuk/articles/00b4615425af6e)
- Databricks 실험(655MB~7GB)에서 pandas-profiling보다 시간·메모리를 덜 썼다는 결론이 있습니다. 다만 수치는 공개하지 않았습니다. [LatentView](https://www.latentview.com/blog/handling-data-at-scale-using-one-line-eda-libraries/)
- Reddit에 "수년간 잘 써 온 도구"라는 댓글이 있습니다. [r/MachineLearning (아카이브 사본)](https://www.reddit.com/r/MachineLearning/comments/1d9plun/sifting_through_data_is_timeconsuming_d/l7io618/)

**3) 반복되는 불만**

(a) 대용량
- [#75 "support big data use cases"](https://github.com/fbdesignpro/sweetviz/issues/75) (open)
- [#102 "sweetviz and large datasets"](https://github.com/fbdesignpro/sweetviz/issues/102)
- [#76](https://github.com/fbdesignpro/sweetviz/issues/76): 3,800열에서 HTML body가 비어서 나옴
- README도 피처 간 연관 분석은 피처 수에 대해 제곱으로 느려진다고 경고합니다. [README](https://github.com/fbdesignpro/sweetviz)

(b) train/test 비교: **지원합니다** (`compare`, `compare_intra`).
- 3개 이상은 비교할 수 없습니다. [#88](https://github.com/fbdesignpro/sweetviz/issues/88)
- `compare_intra` 오류: [#166](https://github.com/fbdesignpro/sweetviz/issues/166) (open)

(c) 타깃 분석: **부분 지원입니다.**
- README에 따르면 불리언과 수치형만 타깃이 될 수 있어서, 범주형·다중 클래스 타깃은 쓸 수 없습니다. [README](https://github.com/fbdesignpro/sweetviz)
- 관련 버그:
  - [#175](https://github.com/fbdesignpro/sweetviz/issues/175) (open): `compare`와 `target_feat`를 함께 쓰면 그래프와 값이 깨짐
  - [#116](https://github.com/fbdesignpro/sweetviz/issues/116): 타깃 비율이 잘못 나옴

(d) 설치·의존성
- numpy 2 비호환 [#189](https://github.com/fbdesignpro/sweetviz/issues/189)가 2025-05에 열렸고, 2026-04 릴리스에서 정리됐습니다.
- 그 이전 이슈:
  - numpy `np.warnings` 오류 [#150](https://github.com/fbdesignpro/sweetviz/issues/150)
  - pandas 2 `iteritems` 오류 [#141](https://github.com/fbdesignpro/sweetviz/issues/141)
- PyPI 분류자에는 Python 3.11까지만 적혀 있습니다. [PyPI](https://pypi.org/project/sweetviz/)

(e) HTML 조작성
- 변수가 90개를 넘으면 연관 그래프 라벨을 읽을 수 없습니다. [#132](https://github.com/fbdesignpro/sweetviz/issues/132)
- 502번째 피처 이후 그래프가 잘렸습니다. [#35](https://github.com/fbdesignpro/sweetviz/issues/35)

(f) Kaggle·Colab
- `show_notebook()`(iframe)을 지원하고, README에 Colab 예제가 있습니다.
- 그러나 README 설치 절에는 Colab처럼 파일 처리가 특수한 환경은 아직 지원하지 않는다고 적혀 있습니다. [README](https://github.com/fbdesignpro/sweetviz)
- 관련 이슈:
  - [#90](https://github.com/fbdesignpro/sweetviz/issues/90) (open): tqdm 오류
  - [#96 "Won't install in Kaggle Notebook"](https://github.com/fbdesignpro/sweetviz/issues/96) (2021)
- Kaggle 기본 이미지에는 들어 있지 않습니다. [kaggle_requirements.txt](https://github.com/Kaggle/docker-python/blob/main/kaggle_requirements.txt)

한글
- 그림에서 글자(glyph) 누락 경고가 나온 이슈가 있습니다. [#23](https://github.com/fbdesignpro/sweetviz/issues/23)

**4) 대회용으로 빠진 것**
- 근거 있음: 범주형·다중 클래스 타깃, 3개 이상 비교(#88), 대용량 처리(#75)
- (추정): 드리프트를 수치로 순위화하는 기능

### 3-3. D-Tale

**1) 요약**
- Flask 서버로 띄우는 브라우저 그리드입니다. 기능은 Describe, 상관, PPS, 결측 분석, 차트, 중복 제거 등입니다. [README](https://github.com/man-group/dtale)
- 2026년에 3.19~3.22를 냈고, pandas 3(3.19.0)과 Python 3.14(3.21.0)에 대응했습니다. [CHANGES.md](https://github.com/man-group/dtale/blob/master/CHANGES.md)

**2) 잘하는 점**
- 엑셀처럼 클릭으로 조작하고, 작업 내용을 코드로 내보낼 수 있습니다. [README](https://github.com/man-group/dtale)
- 온프레미스에서 가장 효율적이었다는 평가가 있습니다. 다만 Databricks에서는 쓸 수 없었다고 합니다. [LatentView](https://www.latentview.com/blog/handling-data-at-scale-using-one-line-eda-libraries/)

**3) 반복되는 불만**

(a) 대용량
- [#276](https://github.com/man-group/dtale/issues/276): 2천만 행에서 느림. 데이터는 메모리에 올라간다는 답변이 달렸습니다.
- [#462](https://github.com/man-group/dtale/issues/462): 23만 행에서도 Describe가 느림
- [#287 "Load data in chunks"](https://github.com/man-group/dtale/issues/287) (open)
- README: ArcticDB를 쓰면 메모리는 줄지만, 100만 행이 넘으면 일부 기능이 꺼집니다. [README](https://github.com/man-group/dtale)

(b) train/test 비교: **없습니다.** README의 기능 목록에 비교가 없고, Merge & Stack이 가장 가까운 기능입니다. [README](https://github.com/man-group/dtale)

(c) 타깃 분석: **부분 지원입니다.**
- 타깃 기준 층화 샘플링은 차트에 반영됐습니다. [#490](https://github.com/man-group/dtale/issues/490)
- 아직 open인 요청:
  - 범주형 컬럼의 타깃별 히스토그램 [#524](https://github.com/man-group/dtale/issues/524)
  - 타깃을 지정하는 "Auto EDA" 리포트 [#497](https://github.com/man-group/dtale/issues/497)

(d) 설치·의존성
- [#877](https://github.com/man-group/dtale/issues/877): numpy 관련 설치 실패 (open, 댓글 18개)
- [#873](https://github.com/man-group/dtale/issues/873): `No module named 'imp'`

(e) 조작성
- Colab에서 groupby 대화상자 일부가 가려져 선택이 안 된다는 댓글이 있습니다. [#766](https://github.com/man-group/dtale/issues/766)
- HN에는 그냥 pandas로 하는 편이 빠르다는 의견도 있습니다. [HN](https://news.ycombinator.com/item?id=31446788)

(f) Kaggle·Colab: **별도 서버가 필요해서 마찰이 큽니다.**
- Colab은 `USE_COLAB=True`가 필요합니다.
- Kaggle은 ngrok과 노트북 인터넷 켜기가 필요하고, ngrok은 분당 20연결로 제한됩니다. [README](https://github.com/man-group/dtale)
- 관련 이슈:
  - [#886](https://github.com/man-group/dtale/issues/886): Colab 업데이트(2024-08-20) 이후 404
  - [#733](https://github.com/man-group/dtale/issues/733) (open): Colab import 오류
  - [#875](https://github.com/man-group/dtale/issues/875) (open): VS Code 노트북 문제

보안
- 웹 서버 구조라 원격 코드 실행(RCE) 취약점 이력이 있습니다. 공개 호스팅한 경우가 대상입니다. [CVE-2024-45595](https://vulert.com/vuln-db/d-tale-vulnerable-to-remote-code-execution-through-the-query-input-on-chart-builder) · [OffSec 분석](https://www.offsec.com/blog/cve-2025-0655/)

한글
- 번역 파일은 `cn`, `en`, `pt`뿐입니다. [translations](https://github.com/man-group/dtale/tree/master/dtale/translations)

**4) 대회용으로 빠진 것**
- 근거 있음: train/test 비교, 타깃 리포트(#497 open)
- 대용량은 메모리 의존입니다(#276).

### 3-4. AutoViz

**1) 요약**
- 한 줄로 차트를 자동 생성합니다. `depVar`로 타깃을 지정하고, `FixDQ()`로 데이터 품질 문제를 고칩니다. [README](https://github.com/AutoViML/AutoViz)
- 마지막 릴리스는 0.1.905(2024-06-10)입니다. [PyPI](https://pypi.org/project/autoviz/)

**2) 잘하는 점**
- 타깃 기준 이변량 차트를 자동으로 그립니다. `chart_format`으로 bokeh, server, html 출력도 고를 수 있습니다. [README](https://github.com/AutoViML/AutoViz)
- Reddit에 이변량 분석을 빠르게 할 수 있다는 댓글이 있습니다. [r/datascience (아카이브 사본)](https://www.reddit.com/r/datascience/comments/1cxhowo/handed_a_dataset_and_told_to_do_data_science_on_it/l577ya5/)

**3) 반복되는 불만**

(a) 대용량
- 기본값이 `max_rows_analyzed=150000`(샘플링), `max_cols_analyzed=30`입니다. [README](https://github.com/AutoViML/AutoViz)
- [#37](https://github.com/AutoViML/AutoViz/issues/37): 10만 행을 처리하지 못함
- [#83](https://github.com/AutoViML/AutoViz/issues/83): 5분 넘게 돌아도 플롯이 안 나옴

(b) train/test 비교: **없습니다.** README에 기능이 없고, 관련 이슈는 질문 수준입니다. [#42](https://github.com/AutoViML/AutoViz/issues/42)

(c) 타깃 분석: **`depVar`로 지원합니다.** 다만 버그가 있습니다.
- [#31](https://github.com/AutoViML/AutoViz/issues/31): 연속형 타깃을 범주로 오인
- [#69](https://github.com/AutoViML/AutoViz/issues/69): depVar가 int32이면 IndexError

(d) 설치·의존성: **가장 큰 약점입니다.**
- [#98](https://github.com/AutoViML/AutoViz/issues/98): Python 3.11에서 holoviews 문제로 `inspect.ArgSpec` 오류 (댓글 32개)
- [#88](https://github.com/AutoViML/AutoViz/issues/88): import 오류
- [#86](https://github.com/AutoViML/AutoViz/issues/86): 새로 설치해도 import에서 실패

(e) 출력
- 리포트 하나가 아니라 차트 묶음이거나 `AutoViz_Plots` 폴더의 HTML 파일들입니다. [README](https://github.com/AutoViML/AutoViz)

(f) Kaggle
- [#115](https://github.com/AutoViML/AutoViz/issues/115): Kaggle 설치 문제(2024-11). 메인테이너는 동작하는 Kaggle 노트북을 제시했습니다.

**4) 대회용으로 빠진 것**
- train/test 비교가 없고, 유지보수가 멈췄습니다.

### 3-5. DataPrep.EDA

**1) 요약**
- Dask 기반이고, `create_report`, `plot`, `plot_correlation`, `plot_missing`, `plot_diff`를 제공합니다. [README](https://github.com/sfu-db/dataprep)
- 최신 0.4.5(2022-08)는 Python <3.11, pandas <2.0, numpy <2.0을 요구합니다. [PyPI](https://pypi.org/project/dataprep/)

**2) 잘하는 점**
- README가 내세우는 점: pandas 기반 도구보다 10배 빠르고, 인터랙티브 시각화를 만들고, Dask 대용량을 지원합니다. [README](https://github.com/sfu-db/dataprep)
- 저자 측 SIGMOD 2021 논문
  - Kaggle 데이터셋 15개에서 pandas-profiling보다 4~20.8배 빨랐습니다.
  - 일부 상관 계산을 끈 상태의 비교입니다.
  - [논문](https://ar5iv.labs.arxiv.org/html/2104.00841)
- 2020년 r/Python 출시글이 1,740점을 받았습니다. [r/Python (아카이브 사본)](https://www.reddit.com/r/Python/comments/hlqnim/understand_your_data_with_a_few_lines_of_code_in/)

**3) 반복되는 불만**

(b) train/test 비교: **부분 지원입니다.**
- `plot_diff([df1, df2])`로 여러 데이터프레임을 비교할 수 있습니다. [문서](https://docs.dataprep.ai/user_guide/eda/plot_diff.html)
- 비교 리포트 요청 [#702](https://github.com/sfu-db/dataprep/issues/702)는 open입니다.

(c) 타깃 분석: **부분 지원입니다.**
- `plot(df, x, y)`는 되지만 `create_report`에는 target 인자가 없습니다. [#954](https://github.com/sfu-db/dataprep/issues/954) (open)

(d) 설치·의존성: **치명적입니다.**
- open 상태인 요청:
  - pandas 2 지원 [#959](https://github.com/sfu-db/dataprep/issues/959)
  - Python 3.12 지원 [#994](https://github.com/sfu-db/dataprep/issues/994): 프로젝트가 아직 활동 중인지 묻는 내용입니다.
- 기본 브랜치에 Python 3.12 대응 커밋이 있지만 배포되지 않았습니다. [pyproject.toml](https://github.com/sfu-db/dataprep/blob/develop/pyproject.toml)

(f) Colab
- "EDA demo doesn't work in google colab" [#996](https://github.com/sfu-db/dataprep/issues/996) (2025-02, open)
- 현재 Python 3.13 환경에서는 pip가 Python 제한이 없는 옛 버전(예: 0.4.1)으로 내려갈 수 있습니다. 그 버전은 pandas <2.0을 요구합니다. [0.4.1 메타데이터](https://pypi.org/project/dataprep/0.4.1/)
  - 실제 설치 성공 여부는 확인 못 함입니다 (실패 가능성이 높다고 추정).

**4) 대회용으로 빠진 것**
- 지금 Kaggle·Colab에서 쓸 수 없는 것이 사실상 전부입니다(#996).

### 3-6. Lux

**1) 요약**
- pandas 데이터프레임을 출력하면 시각화를 자동 추천하는 위젯입니다. `df.intent`로 관심 컬럼을 지정합니다. [문서](https://lux-api.readthedocs.io/en/latest/source/getting_started/overview.html)

**2) 상태: 사실상 중단입니다.**
- PyPI 마지막 릴리스가 2022-02-19입니다. [PyPI](https://pypi.org/project/lux-api/)
- 기본 브랜치 마지막 커밋은 2023-07-04 "pin pandas to 1.4"입니다. [commits](https://github.com/lux-org/lux/commits/master)
- 2024~2025년 이슈에 응답이 없습니다(댓글 0개). [#506](https://github.com/lux-org/lux/issues/506) · [#507](https://github.com/lux-org/lux/issues/507) · [#510](https://github.com/lux-org/lux/issues/510)

**3) 불만**
- 대용량: 1만 행이 넘으면 샘플링하고 상한은 3만 행입니다. [config 문서](https://lux-api.readthedocs.io/en/latest/source/reference/config.html)
- 호환성:
  - pandas 버전이 오르면 집계가 깨집니다. [#492](https://github.com/lux-org/lux/issues/492)
  - JupyterLab 4에서 위젯을 불러오지 못합니다. [#502](https://github.com/lux-org/lux/issues/502)
  - Python 3.13에서 렌더링이 실패합니다. [#511](https://github.com/lux-org/lux/issues/511)
- Colab은 커스텀 위젯 매니저를 켜야 동작한다는 댓글이 있습니다. [#169](https://github.com/lux-org/lux/issues/169)

**4) 대회용으로 빠진 것**
- 현재 환경에서 쓰기 어렵습니다(위 호환성 이슈). train/test 비교도 없습니다 (추정).

### 3-7. PyGWalker (Graphic Walker)

**1) 요약**
- 노트북 안에서 Tableau식 드래그 앤 드롭 시각화를 제공합니다.
- pandas, polars, pyarrow를 지원합니다. README가 Jupyter, Colab, Kaggle, VS Code, marimo, Streamlit을 테스트된 환경으로 명시합니다. [README](https://github.com/Kanaries/pygwalker)

**2) 잘하는 점**
- 스타 약 1.6만으로 이 목록에서 가장 많습니다(2절 표).
- Show HN에서 호평을 받았습니다. [HN](https://news.ycombinator.com/item?id=34869244)
- `privacy="offline"` 모드를 지원합니다. [README](https://github.com/Kanaries/pygwalker)
- 대용량은 `computation="kernel"`(DuckDB)로 처리합니다. [README](https://github.com/Kanaries/pygwalker)

**3) 반복되는 불만**

(a) 대용량
- [#546](https://github.com/Kanaries/pygwalker/issues/546): 368만 행이 렌더링되지 않았습니다. 메인테이너는 distinct 값이 100만을 넘으면 프론트엔드 안전 제한에 걸린다고 설명했습니다.
- [#723](https://github.com/Kanaries/pygwalker/issues/723): 메모리 누수

(b)(c) train/test 비교·타깃 분석: 전용 기능은 확인하지 못했습니다. 직접 끌어다 놓는 수동 방식입니다 (추정).
- 논문도 사용자가 도구 고유의 조작법을 익혀야 하는 점을 한계로 꼽습니다. [arXiv](https://arxiv.org/html/2406.11637v1)

(d) 설치·의존성
- [#717](https://github.com/Kanaries/pygwalker/issues/717): Python 3.13에서 import 실패 (해결됨)
- [#743](https://github.com/Kanaries/pygwalker/issues/743) (open): 최신 Streamlit과 ImportError

(f) Kaggle
- 메인테이너 설명에 따르면 Kaggle에서 페이지를 새로고침하면 커널과의 ipywidgets 통신이 끊깁니다. [#208](https://github.com/Kanaries/pygwalker/issues/208)
- 공식 Kaggle 가이드(한국어판)는 버전을 저장할 때 출력 저장 설정을 켜라고 안내합니다. [가이드](https://docs.kanaries.net/ko/pygwalker/tutorials/use-pygwalker-in-kaggle)

한글
- 내장 locale은 `en-US`, `ja-JP`, `zh-CN`뿐입니다. [locales](https://github.com/Kanaries/graphic-walker/tree/main/packages/graphic-walker/src/locales)
- 한글 컬럼명으로는 계산 필드를 만들 수 없고 CSV 내보내기에서 한글이 깨진다는 이슈 [#507](https://github.com/Kanaries/graphic-walker/issues/507)이 open입니다. 한국어 지원 PR [#506](https://github.com/Kanaries/graphic-walker/pull/506)은 병합되지 않고 닫혔습니다.

**4) 대회용으로 빠진 것**
- 자동 요약, 경고, 비교, 타깃 분석이 없는 "수동 탐색기"입니다 (추정, 위 README 기능 범위 기준).

### 3-8. Mito (mitosheet)

**1) 요약**
- JupyterLab 안의 스프레드시트입니다. 조작하면 pandas 코드가 생성됩니다. [README](https://github.com/mito-ds/mito)
- 저장소 설명이 "AI Chat, Autocomplete, Spreadsheet"로 바뀌었습니다. mito-ai는 2024-09에 처음 릴리스됐습니다. [repo](https://github.com/mito-ds/mito) · [mito-ai PyPI](https://pypi.org/project/mito-ai/)

**2) 잘하는 점**
- 엑셀 사용자를 Python으로 이어 주는 다리라는 평가가 있습니다. [HN](https://news.ycombinator.com/item?id=31447194)

**3) 불만**
- 대용량: [#634 "Performance issues on large datasets"](https://github.com/mito-ds/mito/issues/634) (open)
- Colab: 메인테이너가 "현재 Colab은 지원하지 않는다"고 답했습니다(2023). [#877](https://github.com/mito-ds/mito/issues/877)
- 설치: Python 3.12 미지원 이슈 [#1000](https://github.com/mito-ds/mito/issues/1000)이 아직 open입니다.
  - 다만 현재 PyPI 분류자에는 3.12와 3.13이 적혀 있습니다. [PyPI](https://pypi.org/project/mitosheet/)
- 텔레메트리: 무료판에서는 끌 수 없고 Pro로 업그레이드하라는 안내가 있습니다. [요금제](https://trymito.io/plans) · [HN 비판](https://news.ycombinator.com/item?id=31447945)

**4) 대회용으로 빠진 것**
- train/test 비교와 타깃 분석이 없습니다 (추정). Colab도 지원하지 않습니다(#877).

### 3-9. Microsoft Data Wrangler

**1) 요약**
- VS Code와 VS Code Jupyter용 데이터 뷰어·정제 도구입니다. Data Summary, 컬럼 인사이트를 보여 주고 pandas 코드를 생성합니다. [VS Code 문서](https://code.visualstudio.com/docs/datascience/data-wrangler) · [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler)
- 1.22에서 Polars와 NumPy 출력 렌더러가 옵트인으로 들어왔습니다. [CHANGELOG](https://github.com/microsoft/vscode-data-wrangler/blob/main/CHANGELOG.md)

**2) 잘하는 점**
- 설치 약 236만, 평점 4.5(74명)입니다. [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler)
- CSV 탐색에 쓰는 기본 도구라는 사용자 언급이 있습니다. [#409](https://github.com/microsoft/vscode-data-wrangler/issues/409)

**3) 불만**
- 대용량: 200만 행 × 6열에서 필터 하나에 약 1분이 걸렸습니다. 메인테이너는 pandas가 병목이라고 답했습니다. [#209](https://github.com/microsoft/vscode-data-wrangler/issues/209)
- Polars 요청: [#622](https://github.com/microsoft/vscode-data-wrangler/issues/622) · [#658](https://github.com/microsoft/vscode-data-wrangler/issues/658)
- pandas 3: 렌더러가 동작하지 않습니다. [#631](https://github.com/microsoft/vscode-data-wrangler/issues/631) (open)
- 환경 제약
  - 라이선스상 Visual Studio 제품군에서만 쓸 수 있습니다. [라이선스](https://ms-toolsai.gallerycdn.vsassets.io/extensions/ms-toolsai/datawrangler/1.24.2/1781080568046/Microsoft.VisualStudio.Services.Content.License)
  - Open VSX에는 배포하지 않습니다. [#165](https://github.com/microsoft/vscode-data-wrangler/issues/165)
  - 그래서 Kaggle이나 Colab 웹 노트북에서는 쓸 수 없습니다 (추정).
- 텔레메트리: 사용 데이터를 Microsoft로 전송합니다. [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler)

한글
- 매니페스트에 `l10n` 폴더가 있고, 중국어로 현지화된 오류 문구가 이슈에 찍혀 있습니다. [매니페스트](https://ms-toolsai.gallerycdn.vsassets.io/extensions/ms-toolsai/datawrangler/1.24.2/1781080568046/Microsoft.VisualStudio.Code.Manifest) · [#564](https://github.com/microsoft/vscode-data-wrangler/issues/564)
- 한국어 번들이 있는지는 확인 못 함입니다.

**4) 대회용으로 빠진 것**
- 비교·타깃 분석 언급이 없습니다 (추정). VS Code에 묶여 있습니다.

### 3-10. skimpy / dabl / klib

**skimpy**
- 요약: R의 skimr처럼 콘솔에 유형별 요약통계와 텍스트 히스토그램을 보여 줍니다. pandas와 Polars를 지원합니다. [README](https://github.com/aeturrell/skimpy)
- 요구 사항: Python 3.11 이상, numpy 2 이상. [PyPI](https://pypi.org/project/skimpy/)
- 남은 문제: Windows 글자 표시 문제 [#1048](https://github.com/aeturrell/skimpy/issues/1048), 중복 컬럼명 오류 [#918](https://github.com/aeturrell/skimpy/issues/918)
- 비교, 타깃 분석, 대용량 관련 언급은 README에 없습니다.

**dabl**
- `dabl.plot(X, target_col=...)`은 타깃이 분류인지 회귀인지 판별해서 그에 맞는 그림을 그립니다. [dabl.plot 문서](https://dabl.github.io/stable/generated/dabl.plot.html)
- 사용자 가이드는 현재 구현이 초보적이고 휴리스틱에 많이 의존한다고 밝힙니다. [user guide](https://dabl.github.io/stable/user_guide.html)
- open 이슈: [#340 "dabl.plot dislikes categorical features"](https://github.com/dabl/dabl/issues/340), [#350](https://github.com/dabl/dabl/issues/350) (문서 CI 실패)

**klib**
- `corr_plot(df, target=...)`처럼 타깃과의 상관을 볼 수 있고, `corr_interactive_plot`(Plotly)도 있습니다. 정제 함수(`data_cleaning`, `convert_datatypes` 등)가 같이 들어 있습니다. [README](https://github.com/akanz1/klib)
- 한 튜토리얼은 dtype 변환으로 메모리를 1.3GB에서 200MB로 줄였다고 보고합니다. 작성자가 라이브러리 개발자 본인인지는 확인 못 함입니다. [TDS](https://towardsdatascience.com/data-preparation-with-klib-ec4add15303a/)

**세 도구 공통으로 빠진 것**
- 리포트, train/test 비교, 인터랙티브 UI가 없습니다 (추정, 각 README 기능 범위 기준).

---

## 4. 이슈 키워드 건수 (참고용, 잡음 큼)

- 검색식: `repo:<저장소> is:issue <키워드>` (GitHub Search API, 2026-10-17)
- 본문과 이슈 템플릿까지 검색되므로 규모 감만 보세요.

| 저장소 | memory | slow | colab | kaggle | numpy | install |
|---|---|---|---|---|---|---|
| [fg-data-profiling](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues) | 71 | 19 | 66 | 42 | 248 | 230 |
| [sweetviz](https://github.com/fbdesignpro/sweetviz/issues) | 9 | 0 | 9 | 5 | 20 | 32 |
| [dtale](https://github.com/man-group/dtale/issues) | 27 | 11 | 21 | 10 | 53 | 79 |
| [AutoViz](https://github.com/AutoViML/AutoViz/issues) | 1 | 1 | 10 | 13 | 11 | 48 |
| [dataprep](https://github.com/sfu-db/dataprep/issues) | 9 | 3 | 14 | 14 | 27 | 47 |
| [lux](https://github.com/lux-org/lux/issues) | 3 | 7 | 2 | 8 | 14 | 65 |
| [pygwalker](https://github.com/Kanaries/pygwalker/issues) | 14 | 4 | 4 | 7 | 7 | 67 |
| [mito](https://github.com/mito-ds/mito/issues) | 1 | 7 | 2 | 4 | 10 | 39 |
| [vscode-data-wrangler](https://github.com/microsoft/vscode-data-wrangler/issues) | 288 | 11 | 0 | 0 | 98 | 335 |

Data Wrangler의 memory 288건은 이슈 템플릿 때문에 생긴 잡음으로 보입니다.

---

## 5. 2024~2026년 새로 나왔거나 떠오른 도구

| 도구 | 형태 · 라이선스 | 시작 / 최신 | 대회 관련 포인트 |
|---|---|---|---|
| **skrub `TableReport`** | 라이브러리, 노트북 HTML · BSD-3 | 0.3.0(2024-08)에 추가 / 0.11.0(2026-10-01), ★1,655 | 한 줄로 표·통계·분포·연관성 탭을 만듭니다. pandas와 Polars를 지원하고, 브라우저 안에서만 도는 데모도 있습니다. train/test 비교는 문서에 없습니다. [문서](https://skrub-data.org/stable/reference/generated/skrub.TableReport.html) · [CHANGES](https://skrub-data.org/stable/CHANGES.html) · [브라우저 데모](https://skrub-data.org/skrub-reports/) |
| **Buckaroo** | 노트북 위젯 · BSD-3 | 2023-04 / 0.15.10(2026-10-06), ★685 | pandas·Polars 표시를 히스토그램과 요약통계가 붙은 그리드로 바꿉니다. 10k 행이 넘으면 다운샘플합니다. Colab 지원을 명시합니다. Show HN 105점. [GitHub](https://github.com/buckaroo-data/buckaroo) · [Feature Reference](https://buckaroo-data.readthedocs.io/en/latest/feature_reference.html) · [HN](https://news.ycombinator.com/item?id=44022265) |
| **Deepchecks `train_test_validation`** (신규 아님) | 라이브러리 · AGPL-3.0 | 2021-10 / 0.19.1(2024-12-15), ★4,063 | train과 test만 넣으면 피처·라벨·다변량 드리프트, 새 카테고리, 누수 등을 점검합니다. 다변량 드리프트는 train/test를 구분하는 분류기의 AUC로 재는 방식이라 사실상 adversarial validation입니다. 기본은 1만 행 샘플입니다. [퀵스타트](https://docs.deepchecks.com/0.19/tabular/auto_tutorials/quickstarts/plot_quick_train_test_validation.html) · [드리프트 가이드](https://docs.deepchecks.com/dev/general/guides/drift_guide.html) |
| **Evidently** (신규 아님) | 라이브러리 · Apache-2.0 | 2020-11 / 0.7.23(2026-09-11), ★7,991 | reference와 current 데이터의 컬럼별 드리프트를 통계검정으로 보고합니다. 0.7(2025-04)에서 API가 바뀌었습니다. 구 문서에 Colab·Kaggle 설치법이 있습니다. [README](https://github.com/evidentlyai/evidently) · [마이그레이션](https://docs.evidentlyai.com/faq/migration.md) · [구 튜토리얼](https://docs-old.evidentlyai.com/tutorials-and-examples/tutorial_reports_tests) |
| Colab Data Science Agent | Colab 내장 LLM 에이전트 · 구글 독점 | 2025-03-03 공개 | 데이터와 목표를 주면 노트북을 생성합니다. 연령과 지역·언어 제한이 있습니다. [구글 블로그](https://developers.googleblog.com/en/data-science-agent-in-colab-with-gemini) |
| Positron Data Explorer | 데스크톱 IDE · Elastic License 2.0 | 2025 정식 출시 / 2026.10.0 | 그리드와 요약 패널, DuckDB로 파일 열기를 지원합니다. Kaggle·Colab에서는 쓸 수 없습니다. [문서](https://positron.posit.co/data-explorer.html) |
| quak | anywidget · MIT | 2024-06 / 0.3.5(2026-04-16), ★412 | DuckDB 기반 교차 필터 프로파일러로, 작업을 SQL로 내보낼 수 있습니다. [GitHub](https://github.com/manzt/quak) |
| DuckDB Local UI | 로컬 웹 UI · UI 본체 비공개 | 2025-03-12 | 컬럼 히스토그램, NULL 비율, 카디널리티를 보여 줍니다. HN 926점. [DuckDB 블로그](https://duckdb.org/2025/03/12/duckdb-ui.html) · [HN](https://news.ycombinator.com/item?id=43342712) |
| marimo 테이블 탐색기 + molab | 노트북 · Apache-2.0 | molab 2025-07-18 출시 | 데이터프레임 컬럼 탐색기와 무료 클라우드 노트북입니다. [문서](https://docs.marimo.io/guides/working_with_data/dataframes/) · [molab 발표](https://marimo.io/blog/announcing-molab) |
| Microsoft Data Formulator | 로컬 웹앱 (LLM 필요) · MIT | 2024-10 / v0.7, ★17,569 | 차트 중심 탐색 도구입니다. UI는 영어와 중국어뿐입니다. [GitHub](https://github.com/microsoft/data-formulator) |
| yaEDA | 라이브러리 · MIT | 2026-09-20 첫 릴리스 / 0.1.3(2026-09-28) | "대회용"을 표방합니다. train/test 드리프트, unseen 범주, 대용량 minimal 프리셋을 내세우지만 검증 이력이 없습니다. [PyPI](https://pypi.org/project/yaeda/) |

**제외하거나 저조한 것**
- edvart: 2026-02에 archived됐습니다. [repo](https://github.com/datamole-ai/edvart)
- Kanaries RATH: 마지막 릴리스가 2.1.0(2023-08-25)이고 AGPL-3.0입니다. [repo](https://github.com/Kanaries/Rath)
- PAIR Facets: 2023년에 archived됐습니다. [repo](https://github.com/PAIR-code/facets)
- 한국에서 만든 자동 EDA 도구: 한국어 검색으로 찾지 못했습니다. 결과가 대부분 반도체 설계 쪽 "EDA"였습니다.

---

## 6. 최종 요약표

**표기 기준**
- O = 지원, X = 미지원, 부분 = 제약 있음, ? = 확인 못 함
- (추정) = 공식 문서나 이슈에 언급이 없어서 내린 판단
- "최근 유지보수" O = 최근 12개월 안에 PyPI나 Marketplace 릴리스가 있음 (2026-10-17 기준)

| 도구 | train/test 비교 | 타깃 분석 | 대용량 (수백만 행) | 인터랙티브 | 오프라인·로컬 | 최근 유지보수 | 한국어 UI |
|---|---|---|---|---|---|---|---|
| ydata→fg-data-profiling | O [문서](https://docs.profiling.ydata.ai/latest/features/comparing_datasets/) (2개까지) | 부분 interactions.targets뿐 [#513](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/513) | 부분 minimal·샘플링 필요 [문서](https://docs.profiling.ydata.ai/latest/features/big_data/), [#1579](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1579) | 부분 정적 HTML [#1579](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1579) | O Kaggle 기본 포함 [req](https://github.com/Kaggle/docker-python/blob/main/kaggle_requirements.txt) | O 4.20.0 (2026-09), 단 pandas<3 [PyPI](https://pypi.org/project/fg-data-profiling/) | X CJK 깨짐 [#1876](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1876) |
| Sweetviz | O [README](https://github.com/fbdesignpro/sweetviz) (2개까지 [#88](https://github.com/fbdesignpro/sweetviz/issues/88)) | 부분 불리언·수치형만 [README](https://github.com/fbdesignpro/sweetviz) | 부분 [#75](https://github.com/fbdesignpro/sweetviz/issues/75), [#102](https://github.com/fbdesignpro/sweetviz/issues/102) | 부분 HTML 호버·클릭 [dataroots](https://dev.to/dataroots/streamlining-data-exploration-a-comparison-of-profiling-tools-for-effective-eda-160p) | O 자체 완결 HTML [KDnuggets](https://www.kdnuggets.com/2021/02/powerful-exploratory-data-analysis-sweetviz.html) | 부분 2.5년 공백 후 2026-04 [PyPI](https://pypi.org/project/sweetviz/#history) | X (추정) 글자 누락 [#23](https://github.com/fbdesignpro/sweetviz/issues/23) |
| D-Tale | X [README](https://github.com/man-group/dtale) | 부분 [#490](https://github.com/man-group/dtale/issues/490), [#524](https://github.com/man-group/dtale/issues/524) | 부분 메모리 적재 [#276](https://github.com/man-group/dtale/issues/276) | O [README](https://github.com/man-group/dtale) | 부분 로컬 O, Kaggle은 ngrok 필요 [README](https://github.com/man-group/dtale) | O [CHANGES](https://github.com/man-group/dtale/blob/master/CHANGES.md) | X cn/en/pt만 [translations](https://github.com/man-group/dtale/tree/master/dtale/translations) |
| AutoViz | X [#42](https://github.com/AutoViML/AutoViz/issues/42) | O depVar [README](https://github.com/AutoViML/AutoViz) | 부분 15만 행 샘플 [README](https://github.com/AutoViML/AutoViz) | 부분 bokeh·html 옵션 [README](https://github.com/AutoViML/AutoViz) | O [README](https://github.com/AutoViML/AutoViz) | X 2024-06 [PyPI](https://pypi.org/project/autoviz/) | X (추정) [README](https://github.com/AutoViML/AutoViz) |
| DataPrep.EDA | 부분 plot_diff [문서](https://docs.dataprep.ai/user_guide/eda/plot_diff.html), [#702](https://github.com/sfu-db/dataprep/issues/702) | 부분 plot(x,y)만 [#954](https://github.com/sfu-db/dataprep/issues/954) | 부분 Dask [README](https://github.com/sfu-db/dataprep) | O Bokeh [README](https://github.com/sfu-db/dataprep) | O, 단 설치 불가 수준 [#996](https://github.com/sfu-db/dataprep/issues/996) | X 2022-08, Py<3.11 [PyPI](https://pypi.org/project/dataprep/) | X (추정) [README](https://github.com/sfu-db/dataprep) |
| Lux | X (추정) [문서](https://lux-api.readthedocs.io/en/latest/source/getting_started/overview.html) | 부분 intent [문서](https://lux-api.readthedocs.io/en/latest/source/getting_started/overview.html) | X 3만 행 상한 [config](https://lux-api.readthedocs.io/en/latest/source/reference/config.html) | O 위젯 [README](https://github.com/lux-org/lux) | O (추정) [README](https://github.com/lux-org/lux) | X 2022-02 [PyPI](https://pypi.org/project/lux-api/) | X (추정) [README](https://github.com/lux-org/lux) |
| PyGWalker | X (추정) [arXiv](https://arxiv.org/html/2406.11637v1) | X (추정, 수동) [README](https://github.com/Kanaries/pygwalker) | 부분 DuckDB, distinct 100만 제한 [#546](https://github.com/Kanaries/pygwalker/issues/546) | O [README](https://github.com/Kanaries/pygwalker) | O offline 모드 [README](https://github.com/Kanaries/pygwalker) | O 2026-04 [PyPI](https://pypi.org/project/pygwalker/) | X en/ja/zh만 [locales](https://github.com/Kanaries/graphic-walker/tree/main/packages/graphic-walker/src/locales), 한글 버그 [#507](https://github.com/Kanaries/graphic-walker/issues/507) |
| Mito | X (추정) [README](https://github.com/mito-ds/mito) | X (추정) [README](https://github.com/mito-ds/mito) | X [#634](https://github.com/mito-ds/mito/issues/634) | O [README](https://github.com/mito-ds/mito) | 부분 무료판 텔레메트리 못 끔 [plans](https://trymito.io/plans) | O, 단 AI 중심 [PyPI](https://pypi.org/project/mitosheet/) | ? 확인 못 함 |
| Data Wrangler | X (추정) [문서](https://code.visualstudio.com/docs/datascience/data-wrangler) | X (추정) [문서](https://code.visualstudio.com/docs/datascience/data-wrangler) | 부분 pandas 병목 [#209](https://github.com/microsoft/vscode-data-wrangler/issues/209) | O [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler) | 부분 VS Code 전용, 텔레메트리 [라이선스](https://ms-toolsai.gallerycdn.vsassets.io/extensions/ms-toolsai/datawrangler/1.24.2/1781080568046/Microsoft.VisualStudio.Services.Content.License) | O 2026-06 [Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler) | 부분 (추정) l10n 구조 [매니페스트](https://ms-toolsai.gallerycdn.vsassets.io/extensions/ms-toolsai/datawrangler/1.24.2/1781080568046/Microsoft.VisualStudio.Code.Manifest), [#564](https://github.com/microsoft/vscode-data-wrangler/issues/564) |
| skimpy | X (추정) [README](https://github.com/aeturrell/skimpy) | X (추정) [README](https://github.com/aeturrell/skimpy) | ? 확인 못 함 | X 콘솔 표 [README](https://github.com/aeturrell/skimpy) | O [README](https://github.com/aeturrell/skimpy) | O 2026-06 [PyPI](https://pypi.org/project/skimpy/) | X (추정), Windows 글자 문제 [#1048](https://github.com/aeturrell/skimpy/issues/1048) |
| dabl | X (추정) [가이드](https://dabl.github.io/stable/user_guide.html) | O target_col [문서](https://dabl.github.io/stable/generated/dabl.plot.html) | ? 확인 못 함 | X (추정) matplotlib [문서](https://dabl.github.io/stable/generated/dabl.plot.html) | O (추정) | X 2024-12 [PyPI](https://pypi.org/project/dabl/) | X (추정) |
| klib | X (추정) [README](https://github.com/akanz1/klib) | 부분 corr_plot target [README](https://github.com/akanz1/klib) | ? (dtype 축소 사례 [TDS](https://towardsdatascience.com/data-preparation-with-klib-ec4add15303a/)) | 부분 Plotly 상관 [README](https://github.com/akanz1/klib) | O (추정) | O 2026-06 [PyPI](https://pypi.org/project/klib/) | X (추정) |
| skrub TableReport | X [CHANGES](https://skrub-data.org/stable/CHANGES.html) | 부분 (추정) 연관성 탭 [문서](https://skrub-data.org/stable/reference/generated/skrub.TableReport.html) | 부분 열이 많으면 일부 생략 [문서](https://skrub-data.org/stable/reference/generated/skrub.TableReport.html) | O [문서](https://skrub-data.org/stable/reference/generated/skrub.TableReport.html) | O 브라우저 내 실행 [데모](https://skrub-data.org/skrub-reports/) | O 2026-10 [PyPI](https://pypi.org/project/skrub/) | X (추정) |
| Buckaroo | 부분 Compare 예제 앱 [GitHub](https://github.com/buckaroo-data/buckaroo) | X (추정) | 부분 1만 행 다운샘플 [문서](https://buckaroo-data.readthedocs.io/en/latest/feature_reference.html) | O [GitHub](https://github.com/buckaroo-data/buckaroo) | O (추정) | O 2026-10 [PyPI](https://pypi.org/project/buckaroo/) | ? 확인 못 함 |
| Deepchecks | O [퀵스타트](https://docs.deepchecks.com/0.19/tabular/auto_tutorials/quickstarts/plot_quick_train_test_validation.html) | O 라벨 드리프트 [퀵스타트](https://docs.deepchecks.com/0.19/tabular/auto_tutorials/quickstarts/plot_quick_train_test_validation.html) | 부분 1만 행 샘플 [가이드](https://docs.deepchecks.com/dev/general/guides/drift_guide.html) | 부분 HTML (추정) | O (추정) | 부분 PyPI 2024-12 [PyPI](https://pypi.org/project/deepchecks/) | ? 확인 못 함 |
| Evidently | O [README](https://github.com/evidentlyai/evidently) | 부분 (추정) | 부분 시각화 집계 [구 문서](https://docs-old.evidentlyai.com/tutorials-and-examples/tutorial_reports_tests) | 부분 HTML (추정) | O (추정) | O 2026-09 [PyPI](https://pypi.org/project/evidently/) | ? 확인 못 함 |

### 표에서 보이는 빈자리 (위 근거로 바로 도출되는 것만)
- 아래 다섯 가지를 모두 O로 만족하는 도구는 표에 없습니다.
  - train/test 비교
  - 범주형·다중 클래스까지 포함한 타깃 분석
  - 수백만 행 처리
  - Kaggle·Colab 최신 환경(Python 3.13, pandas 3)과의 호환
  - 한국어 UI
- 둘을 함께 하는 도구도 제약이 있습니다.
  - Sweetviz만 비교와 타깃을 함께 하지만, 범주형 타깃이 안 되고 둘을 같이 쓰면 버그가 있습니다([#175](https://github.com/fbdesignpro/sweetviz/issues/175)).
  - Deepchecks는 드리프트를 수치로 보여 주지만, 1만 행 샘플이 기본이고 2024-12 이후 PyPI 릴리스가 없습니다.
- "한 줄 리포트" 계열과 "인터랙티브 탐색" 계열이 나뉘어 있습니다.
  - 리포트 계열(ydata, Sweetviz)은 정적 HTML의 무게 문제가 있습니다([#1579](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1579)).
  - 탐색 계열(D-Tale, PyGWalker, Data Wrangler)은 비교·타깃 자동 분석이 없습니다.
- (추정) 인터넷이 꺼진 대회 노트북에서는 Kaggle 이미지에 미리 들어 있지 않은 도구를 pip로 설치할 수 없습니다. 기본 포함 여부는 [kaggle_requirements.txt](https://github.com/Kaggle/docker-python/blob/main/kaggle_requirements.txt)로 확인했고, 인터넷 차단 규칙 자체는 이번에 확인하지 못했습니다.
