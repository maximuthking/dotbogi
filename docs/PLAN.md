# 돋보기(Dotbogi) 기획서

캐글·데이콘 정형 데이터 대회용 로컬 분석 도구. 작성 2026-10-17.

## 0. 가정 (사용자 확인 없이 정한 것)

- **대상**: 캐글·데이콘의 정형(tabular) 데이터 대회 참가자. 이미지·음성·텍스트 대회 전용 분석은 하지 않습니다.
  - 근거: 사용자의 기존 대회 폴더(`C:\Projects\Dacon`, `kaggle`, `Store_Sales`)가 모두 정형 데이터 + LightGBM/XGBoost/CatBoost + 실험 로그 구조입니다.
- **형태**: 사용자 PC에서 돌아가는 로컬 프로그램. 데이터를 밖으로 보내지 않습니다. 화면은 브라우저로 엽니다.
- **언어**: 한국어 화면. 영어 화면은 이번 범위에서 뺍니다.
- **사용 방식**: 사람이 화면에서 쓰는 것과, 학습 스크립트·AI 에이전트가 한 줄로 기록하는 것을 같은 저장소(대회 폴더의 `.dotbogi/`)로 묶습니다. 사용자가 Codex·Claude 같은 에이전트로 대회를 돌리는 흔적(`AGENTS.md`, 실험별 `metrics.json`)이 있어서입니다.

## 1. 조사한 프로그램 (자세한 근거: `docs/research/`)

| 분류 | 프로그램 | 상태 (2026-10 기준) |
|---|---|---|
| 자동 EDA 리포트 | [ydata-profiling → fg-data-profiling](https://github.com/Data-Centric-AI-Community/fg-data-profiling), [Sweetviz](https://github.com/fbdesignpro/sweetviz) | 유지보수 중. pandas 3 미지원(fg), 2년 반 공백 후 재개(Sweetviz) |
| 인터랙티브 탐색 | [D-Tale](https://github.com/man-group/dtale), [PyGWalker](https://github.com/Kanaries/pygwalker), [Mito](https://github.com/mito-ds/mito), [Data Wrangler](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.datawrangler) | 유지보수 중 |
| 정지된 EDA | [AutoViz](https://pypi.org/project/autoviz/), [DataPrep](https://pypi.org/project/dataprep/), [Lux](https://pypi.org/project/lux-api/), [dabl](https://pypi.org/project/dabl/) | 2022~2024 정지 |
| 검증·드리프트 | [Deepchecks](https://github.com/deepchecks/deepchecks), [Evidently](https://github.com/evidentlyai/evidently), [NannyML](https://github.com/NannyML/nannyml) | Deepchecks 2024-12 정지, NannyML 인수 후 정지 |
| AutoML | [AutoGluon](https://github.com/autogluon/autogluon), [mljar](https://github.com/mljar/mljar-supervised), [PyCaret](https://github.com/pycaret/pycaret), [FLAML](https://github.com/microsoft/FLAML) | AutoGluon·mljar·FLAML 활발 |
| 대회 유틸 | [nyaggle](https://github.com/nyanp/nyaggle), [Kaggler](https://github.com/jeongyoonlee/Kaggler), [Kaggle CLI](https://github.com/Kaggle/kaggle-cli), [kx](https://github.com/RJSIN147/Kaggle-skill) | nyaggle·Kaggler 정지, kx는 별 1 |
| 실험 관리 | [MLflow](https://mlflow.org/docs/latest/ml/tracking/), [W&B](https://github.com/wandb/wandb), [DVC](https://doc.dvc.org/command-reference/exp/show), 구글 시트 | LB 개념 없음 |

## 2. 비교표 (O 지원, △ 일부, X 없음)

| 기능 | ydata/fg | Sweetviz | D-Tale | Deepchecks | nyaggle | MLflow | kx | **돋보기** |
|---|---|---|---|---|---|---|---|---|
| 컬럼 요약·분포 | O | O | O | △ | X | X | △ | O |
| train/test 비교 | O(2개) | O(2개) | X | O | △ | X | △ | O |
| 범주형·다중분류 타깃 분석 | X | X(불리언·수치만) | △ | △ | X | X | X | O |
| 드리프트 수치 순위 | X | X | X | O | X | X | X | O |
| 적대적 검증 | X | X | X | O(1만 행 샘플) | O | X | O | O |
| 누수·ID 순서 점검 | △(경고) | X | △ | △ | X | X | O | O |
| 검증 방법 추천 + 폴드 파일 | X | X | X | X | X | X | △ | O |
| CV↔Public LB 기록·비교 | X | X | X | X | X | △(수동) | O | O |
| OOF 앙상블 | X | X | X | X | O | X | O | O |
| 제출 파일 검사·자동 수정 | X | X | X | X | X | X | △(shape) | O |
| 사람용 화면 | 정적 HTML | 정적 HTML | O | 정적 HTML | X | O | X | O |
| 한국어 화면·한글 컬럼 | X(CJK 깨짐) | X | X | ? | X | X | X | O |
| pandas 3 / Python 3.13+ | X | △ | O | X | X | O | ? | O |
| 데이콘 지원 | - | - | - | - | - | - | X | O |

### 기본기 (거의 다 있는 것 → 꼭 있어야 넘어옴)
컬럼 요약·분포 그림, 결측·고유값 경고, 상관, 데이터 표 보기.

### 차별점 (한두 개만 잘하는 것 → 가져올 후보)
- train/test 나란히 비교 + 타깃 겹쳐 보기 (Sweetviz)
- 경고(Alerts) 목록 (ydata)
- 구분 분류기 AUC로 다변량 드리프트 (Deepchecks, nyaggle)
- OOF·제출 파일을 실험 폴더에 자동 저장 (nyaggle, mljar)
- CV와 LB 어긋남 경보 (kx)
- 자동 피처 예측력(PPS) (D-Tale)

### 빈 자리 (여러 곳의 공통 불만, 아무도 안 하는 것 → 존재 이유)
1. CV와 Public LB를 함께 기록·비교하고 최종 제출을 고르는 화면이 없음. 근거 12건 이상.
2. 제출 파일을 올리기 전에 검사해 주는 도구가 없음(GitHub 검색 0건). 근거 9건.
3. 그룹·시간 구조를 감지해 검증 방법을 추천하는 기능이 없음(폴드 수 자동 선택 수준뿐).
4. 범주형·다중분류 타깃까지 되는 train/test 비교가 없음.
5. 한국어 화면, cp949 CSV, 데이콘 규칙(최종 선택 자동 변경, 하루 제출 한도, 복합 평가식) 지원이 없음.
6. 설치 의존성 문제가 모든 기존 도구의 1순위 불만(Python 3.12·3.13, numpy 2, pandas 3 미지원).

## 3. 설계

### 한 줄 정의
**캐글·데이콘 정형 데이터 대회 참가자가, 데이터를 열자마자 함정(누수·분포 차이·검증 방법)을 알고, 실험 점수와 리더보드를 한 곳에서 비교하고, 제출 파일을 올리기 전에 검사하는 한국어 로컬 도구.**

### 가져올 장점 (출처)
- train/test를 한 그림에 겹쳐 그리고 타깃 관계를 같이 보여주기: Sweetviz ([KDnuggets](https://www.kdnuggets.com/2021/02/powerful-exploratory-data-analysis-sweetviz.html))
- 경고 목록을 첫 화면에: ydata Alerts ([dataroots](https://dev.to/dataroots/streamlining-data-exploration-a-comparison-of-profiling-tools-for-effective-eda-160p))
- 구분 분류기 AUC + 원인 컬럼: Deepchecks Multivariate Drift ([문서](https://docs.deepchecks.com/0.19/tabular/auto_checks/train_test_validation/plot_multivariate_drift.html))
- 실험마다 OOF·test 예측·제출 파일 자동 저장: nyaggle ([문서](https://nyaggle.readthedocs.io/en/latest/source/tutorial/experiment.html))
- CV와 LB 어긋남 경보: kx ([README](https://github.com/RJSIN147/Kaggle-skill))
- OOF hill climbing: 상위권 표준 기법 ([Deotte 1위](https://www.kaggle.com/competitions/playground-series-s5e5/writeups/chris-deotte-1st-place-gpu-hill-climbing))
- Kaggle CLI로 제출 기록 가져오기 ([문서](https://github.com/Kaggle/kaggle-cli/blob/main/docs/competitions.md))

### 고칠 단점
| 기존 불만 (출처) | 돋보기의 해결 |
|---|---|
| 범주형·다중분류 타깃 미지원 (Sweetviz README, ydata [#513](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/513)) | 이진·다중·회귀 모두 타깃 관계와 예측력 계산 |
| 고유값 많은 컬럼이 타깃을 외워 관계가 부풀려짐 (일반적 함정) | 단일 피처 예측력을 OOF 타깃 인코딩으로 계산 |
| HTML 리포트 80MB, 브라우저가 못 엶 ([#1579](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1579)) | 원본 데이터 대신 요약만 담아 수 MB 이하 보고서 |
| 열 수 제곱으로 느려짐 ([#1028](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1028)) | 컬럼별 독립 계산(선형), 진행률 표시, 결과 디스크 캐시 |
| 설치·의존성 (Python 3.12/3.13, numpy 2, pandas 3) | 의존성은 pandas·numpy·scipy·scikit-learn만(캐글·코랩 기본 포함), LightGBM은 있으면 사용 |
| 한국어 없음, CJK 깨짐 ([#1876](https://github.com/Data-Centric-AI-Community/fg-data-profiling/issues/1876), [GW #507](https://github.com/Kanaries/graphic-walker/issues/507)) | 한국어 화면, 한글 컬럼명·cp949 CSV 자동 처리 |
| Deepchecks 1만 행 샘플, 2024-12 정지 | 적대적 검증은 train·test 각 10만 행, 원인 컬럼 제외 후 재실행 |
| 실험 추적기에 LB 개념 없음, 시트 수동 기록 ([Q&A](https://www.kaggle.com/discussions/questions-and-answers/100810)) | CV·Public·Private 대장, 스크립트 한 줄 기록, Kaggle 기록 자동 가져오기 |
| CV-LB 불일치를 판단할 기준이 없음 ([데이콘 405583](https://dacon.io/en/forum/405583)) | CV↔LB 상관·판정, OOF로 Public LB 흔들림 크기 시뮬레이션, 두 실험 승률 |
| 최종 제출 고르기, 데이콘 자동 변경 함정 ([412692](https://dacon.io/en/competitions/official/236336/talkboard/412692)) | 최종 2개 추천과 이유, 데이콘 주의 안내 |
| 제출 형식 실수 (컬럼명, 앞자리 0, 확률/라벨, 인코딩) | 제출 검사 + 의미를 바꾸지 않는 자동 수정본 저장 |
| hill climbing 과적합 (음수 가중치, OOF 과적합) | 양수 가중치만, 폴드 교차로 잰 정직한 앙상블 점수, 기본 모델은 학습 폴드 안쪽으로 조기 종료 |
| 검증 방법 추천 없음 | 시간 분리·그룹 구조 감지 → 추천 + `folds.csv` + 코드 조각 |

### 새로 더할 것 (진짜 차별점)
1. **검증 설계 도우미**: 데이터 구조를 보고 K-Fold/층화/그룹/시간 검증을 이유와 함께 추천, 폴드 파일 생성.
2. **Public LB 흔들림 시뮬레이션**: "이 0.001 차이가 Public 크기에서 의미 있나?"를 OOF로 답함.
3. **정직한 앙상블 점수**: 가중치를 다른 폴드로 검증한 점수를 같이 보여 과적합을 드러냄.
4. **사람 화면 + 스크립트 한 줄**: `dotbogi.log(...)`로 기록하면 화면에 바로 반영.

### 일부러 뺄 것
- 이미지·텍스트·음성 대회 전용 분석: 정형 데이터에 집중해 완성도를 높이려고.
- AutoML·하이퍼파라미터 튜닝: AutoGluon 등이 이미 잘함. 기준 모델 1종(LightGBM, 없으면 HistGradientBoosting)만.
- 클라우드 동기화·팀 서버: 로컬 우선. 공유는 HTML 보고서로.
- 데이콘 자동 제출·점수 수집: 공식 API를 확인 못 함. 점수는 직접 입력.
- 영어 화면: 1차 사용자가 한국어 사용자.
- 피처 엔지니어링 자동 생성·코드 생성: 범위가 너무 커지고 기존 도구(Data Wrangler 등)가 함.

## 4. 화면 구성

| 메뉴 | 내용 |
|---|---|
| 시작 | 최근 대회, 폴더 고르기(파일 자동 탐지 미리보기) |
| 개요 | 파일·행·열, 타깃·과제·지표(바꾸기 가능)와 추론 이유, 타깃 분포, 주의할 점 요약 |
| 데이터 점검 | 15종 점검 결과를 위험·주의·참고로 정렬, 관련 컬럼 바로가기 |
| 컬럼 | 전체 컬럼 표(예측력·분포 차이·결측 정렬), 컬럼 상세(train/test 분포, 통계, 타깃 관계), 종류 변경·제외 |
| train vs test | 적대적 검증(AUC 해석, 원인 컬럼, test 유사도 분포, 컬럼 빼고 다시), 분포 차이 순위 |
| 탐색 | 예측력 순위, 상관 행렬, 그래프 만들기, 데이터 표(정렬·필터) |
| 검증 설계 | 추천과 이유, 폴드 만들기, 폴드 요약, 코드 조각, 기본 모델 교차검증 |
| 실험 | 대장(CV·Public·Private·메모 편집), CV↔LB 그림과 판정, LB 흔들림, 최종 추천, 오늘 제출 수, 추가(파일·스크립트·Kaggle) |
| 앙상블 | 실험 고르기, 상관, 가중치, 정직한 점수, 저장(제출 파일 생성) |
| 제출 검사 | 파일 검사, 자동 수정본, 두 제출 비교 |
| 설정 | 파일 다시 고르기, 대회 정보(플랫폼, Public 비율, 하루 제출 수, 최종 선택 수, 규칙 메모), 사용자 지표 파일, 보고서 내보내기 |

## 5. 완성 기준 ("다 됐다"의 기준)

### 기능
- F1 폴더를 열면 train/test/sample_submission을 찾고 타깃·ID·과제·지표를 추론해 이유를 보여준다. 실제 대회 데이터 4종과 합성 데이터에서 맞게 추론한다.
- F2 모든 컬럼에 train/test 분포 그림, 통계, 타깃 관계, 단일 피처 예측력, 분포 차이 지표가 나온다.
- F3 데이터 점검이 합성 데이터에 심어 둔 문제(누수 컬럼, train-test 같은 행, 시간 분리, 그룹 구조, 새 범주, 숫자인데 문자, 공백만 다른 범주, ID 정렬 누수, 상수 컬럼, 불균형)를 모두 잡는다.
- F4 적대적 검증: 같은 분포면 AUC≈0.5, 심은 차이는 원인 컬럼 1위, 컬럼 제외 후 재실행, 유사도 CSV 저장.
- F5 검증 설계: 시간 분리 → 시간 검증, 그룹 구조 → 그룹 K-Fold, 그 외 → 층화/K-Fold를 추천하고 `folds.csv`를 저장하며 코드 조각을 준다.
- F6 기본 모델: CV·폴드별 점수·중요도, OOF·test 예측·제출 파일 자동 저장, 실험 대장 등록. LightGBM이 없어도 동작.
- F7 실험 대장: 추가·수정·삭제(되살릴 수 있게 휴지통), `dotbogi.log` 기록, OOF·제출 파일로 추가(ID로 맞춤), CV↔LB 그림·상관·판정, LB 흔들림, 최종 추천, 오늘 제출 수.
- F8 앙상블: 2개 이상 고르면 가중치·정직한 점수·상관을 보여주고, 저장하면 제출 파일까지 만든다.
- F9 제출 검사: 10종 이상의 문제를 잡고, 원본을 두고 수정본을 저장하며, 두 제출을 비교한다.
- F10 HTML 보고서를 내보내고, 인터넷 없이 열린다. 수 MB 이하.
- F11 명령줄: `dotbogi [폴더]`, `dotbogi check`, `dotbogi sub-check`(문제 있으면 종료 코드 1), `dotbogi report`.
- F12 Kaggle CLI가 있으면 제출 기록과 점수를 가져와 실험에 붙인다.
- F13 사용자 정의 지표(파이썬 파일)와 Brier·ECE 지표로 데이콘 복합 평가식을 재현할 수 있다.

### 안정성
- S1 잘못된 경로, 빈 파일, 타깃 없음, test 없음, 한쪽에만 있는 컬럼, 전부 결측인 컬럼, 한글 컬럼명, cp949 CSV, 중복 컬럼명에서 깨지지 않는다.
- S2 새로고침·재시작해도 설정·폴드·실험이 남는다(디스크 저장, 쓰기는 임시 파일 후 교체).
- S3 오래 걸리는 작업은 진행률과 남은 시간을 보여주고 화면이 멈추지 않는다. 오류는 한국어로 원인과 할 일을 알려준다.
- S4 서버가 꺼지면 화면에 안내가 뜬다.
- S5 pandas 2.x·3.x, Python 3.10 이상에서 동작한다(3.12 + pandas 2.3, 3.12 + pandas 3.0으로 확인).
- S6 127.0.0.1에만 열리고, 실행할 때 만든 토큰 없이는 API를 쓸 수 없다. 읽기 전용 폴더는 사용자 홈에 저장한다.

### 사용감
- U1 처음 쓰는 사람이 설명 없이 폴더를 열고 점검 결과까지 간다.
- U2 로딩·빈 상태·오류 화면이 모두 있고, 버튼을 누르면 반응이 보인다.
- U3 1280px 노트북부터 큰 모니터까지 깨지지 않는다. 밝은·어두운 테마.
- U4 문구가 한국어로 일관되고, 숫자는 읽기 쉽게(천 단위, 유효숫자) 보인다.

### 성능
- P1 300만 행 × 6열, 70만 행 × 23열 데이터에서 열기 + 컬럼 분석이 각각 30초 안에 끝난다.
- P2 화면 이동은 캐시로 즉시, 큰 표는 페이지 단위로 보낸다.

### 실행·배포
- D1 `pip install`로 설치하고 `dotbogi` 명령으로 실행한다. 윈도우용 실행 배치 파일을 둔다.
- D2 README에 설치·실행·스크립트 연동 방법이 있다.

## 6. 기술 스택과 이유

| 부분 | 선택 | 이유 |
|---|---|---|
| 분석 | Python, pandas(2·3), numpy, scipy, scikit-learn, LightGBM(선택) | 대회 참가자가 이미 쓰는 것. 캐글·코랩 이미지에 기본 포함. 설치 의존성 불만을 피함 |
| 서버 | 표준 라이브러리 `http.server` | 설치할 게 없음. 127.0.0.1 + 토큰으로 안전 |
| 화면 | 빌드 없는 바닐라 JS(ES 모듈) + ECharts 6.1 동봉 | 혼자 AI로 고치기 쉬움, 빌드 도구 불필요, 인터넷 없이 동작 |
| 저장 | 대회 폴더의 `.dotbogi/` (JSON, parquet, csv) | 서버·DB 없음. 폴더째 옮기거나 git에 넣기 쉬움 |
| 배포 | pip 패키지(무료), 실행 배치 파일 | 운영비 0원 |
