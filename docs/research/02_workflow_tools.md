# 대회 워크플로 도구 조사 (검증·AutoML·실험관리·앙상블·제출)

조사일 2026-10-17. 서브에이전트 조사 결과를 정리한 것입니다. 버전·날짜는 PyPI/GitHub API로 직접 조회했습니다. Reddit은 접근이 막혀 근거가 없습니다.

## A. 데이터 검증·드리프트·누수

| 도구 | 상태 | 잘하는 점 | 불만·제약 | 대회용으로 빠진 것 |
|---|---|---|---|---|
| [Deepchecks](https://github.com/deepchecks/deepchecks) | 0.19.1 (2024-12) 이후 릴리스 없음 ([PyPI](https://pypi.org/project/deepchecks/)) | train_test_validation 12종 검사, Multivariate Drift = 구분 분류기 AUC ([문서](https://docs.deepchecks.com/0.19/tabular/auto_checks/train_test_validation/plot_multivariate_drift.html)) | NumPy 2 공식 미지원 ([#2790](https://github.com/deepchecks/deepchecks/issues/2790)), 2026 이슈 무응답 ([#2824](https://github.com/deepchecks/deepchecks/issues/2824)) | OOF·LB·제출 관련 검사 없음 |
| [Evidently](https://github.com/evidentlyai/evidently) | 0.7.23 (2026-09) | 데이터 크기별 검정 자동 선택 ([문서](https://docs.evidentlyai.com/metrics/explainer_drift)) | API가 여러 번 바뀜 ([v0.7.0](https://github.com/evidentlyai/evidently/releases/tag/v0.7.0)), 통계 엣지 케이스 버그 ([#1929](https://github.com/evidentlyai/evidently/issues/1929)) | 탭룰러 domain classifier 없음, 누수 검사 없음 |
| [NannyML](https://github.com/NannyML/nannyml) | 0.13.1 (2025-07), Soda 인수 후 커밋 없음 | DomainClassifier AUROC ([문서](https://nannyml.readthedocs.io/en/stable/how_it_works/multivariate_drift.html)) | Python<3.13, lightgbm<4.6 ([PyPI](https://pypi.org/project/nannyml/)) | 운영 모니터링용 청크 구조 |
| [Great Expectations](https://github.com/fivetran/great_expectations) | 1.24.0 (2026-10) | 범용 품질 검사 | 설치 패키지 107개, 학습 곡선 ([endjin](https://endjin.com/blog/a-look-into-pandera-and-great-expectations-for-data-validation)) | 드리프트·누수 전용 기능 없음 |
| [advertion](https://pypi.org/project/advertion/) | 1.0.1 (2024-12) | adversarial validation 한 함수 | Python<3.12 | 나머지 전부 |
| [autogluon.eda](https://pypi.org/project/autogluon.eda/) | 0.8.3 (2024-05) 정지 | covariate shift 감지 ([문서](https://auto.gluon.ai/0.8.2/tutorials/eda/eda-auto-covariate-shift.html)) | Python<3.11 | 나머지 전부 |

## B. AutoML

| 도구 | 상태 | 잘하는 점 | 불만 |
|---|---|---|---|
| [AutoGluon](https://github.com/autogluon/autogluon) | 1.6.3 (2026-09) | 2024 탭룰러 대회 18개 중 15개 Top3 (사람 개입 포함) ([노트](https://auto.gluon.ai/dev/whats_new/v1.2.0.html)) | 메모리 ([FAQ](https://auto.gluon.ai/dev/tutorials/tabular/tabular-faq.html)), 자체 앙상블보다 직접 hill climbing이 낫다는 입상자 의견 ([S4E9](https://www.kaggle.com/competitions/playground-series-s4e9/discussion/536980)), 같은 fold로 조기 종료해 OOF가 약간 과적합 ([S4E10](https://www.kaggle.com/competitions/playground-series-s4e10/discussion/539539)) |
| [PyCaret](https://github.com/pycaret/pycaret) | 3.3.2 고정 의존성, 4.0 알파는 FSL 라이선스로 전환 | blend/stack API | numpy<1.27, pandas<2.2 고정 ([PyPI](https://pypi.org/project/pycaret/)) |
| [FLAML](https://github.com/microsoft/FLAML) | 2.7.0 (2026-09) | 의존성 1개, 자동 CV | 앙상블에 사용자 CV 미적용 ([#709](https://github.com/microsoft/FLAML/issues/709)) |
| [H2O AutoML](https://docs.h2o.ai/h2o/latest-stable/h2o-docs/automl.html) | 3.46 | Stacked Ensemble | Java, numpy<2, Python≤3.11 ([요구사항](https://docs.h2o.ai/h2o/latest-stable/h2o-docs/welcome.html)) |
| [LightAutoML](https://github.com/sb-ai-lab/LightAutoML) | 0.4.2 (2025-12) | fit_predict가 OOF 반환, WeightedBlender | Kaggle 설치 이슈 ([#147](https://github.com/sb-ai-lab/LightAutoML/issues/147)) |
| [mljar-supervised](https://github.com/mljar/mljar-supervised) | 1.3.2 (2026-07) | 모델별 리포트, Compete 모드, OOF csv | 의존 라이브러리 변경 때 깨짐 ([#691](https://github.com/mljar/mljar-supervised/issues/691)) |

## C. 대회 전용 유틸

- [Kaggler](https://github.com/jeongyoonlee/Kaggler): 2022-03 마지막 릴리스, Cython 빌드 실패 ([#77](https://github.com/jeongyoonlee/Kaggler/issues/77)).
- [Kaggle 공식 CLI](https://github.com/Kaggle/kaggle-cli): `competitions submissions`로 점수 조회, CSV·JSON 출력 ([문서](https://github.com/Kaggle/kaggle-cli/blob/main/docs/competitions.md)). 목록 개수 제한 ([#166](https://github.com/Kaggle/kaggle-cli/issues/166)). 형식 오류는 채점 뒤에야 확인.
- [nyaggle](https://github.com/nyanp/nyaggle): run_experiment로 OOF·제출 저장, adversarial_validate, averaging_opt. 2023-07 이후 정지, LightGBM 4 비호환 ([#112](https://github.com/nyanp/nyaggle/issues/112)). LB 연결 없음.

## D. 실험 관리

- [MLflow](https://mlflow.org/docs/latest/ml/tracking/), [DVC](https://doc.dvc.org/command-reference/exp/show), [Aim](https://github.com/aimhubio/aim), [ClearML](https://github.com/clearml/clearml), [W&B](https://github.com/wandb/wandb): 모두 LB 점수 자리가 따로 없어 수동 metric으로 기록. W&B는 계정 필수, ClearML 서버는 SSPL·Docker, Aim은 Linux/macOS만 명시.
- [Neptune](https://www.infoworld.com/article/4101200/openai-to-acquire-ai-training-tracker-neptune.html): 2026-03 서비스 종료.
- 참가자 관행: 구글 시트에 CV/LB 기록 ([Kaggle Q&A 100810](https://www.kaggle.com/discussions/questions-and-answers/100810), [168520](https://www.kaggle.com/discussions/questions-and-answers/168520)). 시트 기록의 불편 ([게스트 글](https://thesequence.substack.com/p/guest-post-switching-from-spreadsheets)). Kaggle 공식 문서 "Avoid chasing the public leaderboard" ([문서](https://www.kaggle.com/docs/competitions)).

## E. 앙상블

- Chris Deotte 1위: OOF hill climbing으로 수백 개 중 7개 선택 ([S5E5](https://www.kaggle.com/competitions/playground-series-s5e5/writeups/chris-deotte-1st-place-gpu-hill-climbing)).
- 함정: 음수 가중치 과적합, 순서 의존성 ([S5E5 5위](https://www.kaggle.com/competitions/playground-series-s5e5/writeups/alan1305-5th-place-solution-ensemble-of-68-models), [S4E10](https://www.kaggle.com/competitions/playground-series-s4e10/discussion/539539)).
- [hillclimbers](https://github.com/Matt-OP/hillclimbers) 2023-06 정지, [vecstack](https://github.com/vecxoz/vecstack) 0.5.2.

## F. 제출 파일 검증

- 전용 도구 없음: GitHub 검색 "kaggle submission validator" 0건 ([검색](https://github.com/search?q=kaggle+submission+validator&type=repositories)).
- DrivenData 커뮤니티는 pandas assert를 직접 짜라고 권함 ([글](https://community.drivendata.org/t/what-could-possibly-be-going-wrong-with-the-submission/10797)).
- 데이콘: [`dacon` 패키지](https://pypi.org/project/dacon/)는 2022년 다운로드용 메모 수준. 제출·점수 API 확인 못 함.
