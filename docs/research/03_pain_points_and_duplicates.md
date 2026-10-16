# 대회 참가자 불편과 중복 도구 조사

조사일 2026-10-17. 서브에이전트 조사 결과 정리. Reddit·캐글코리아(페이스북)는 접근이 막혀 근거가 없습니다. Kaggle 토론 일부는 검색 요약으로만 확인했습니다(표시).

## 1. 이미 비슷한 도구가 있는지

| 도구 | 형태 | 겹치는 기능 | 상태 | 겹침 |
|---|---|---|---|---|
| [kx (Kaggle-skill)](https://github.com/RJSIN147/Kaggle-skill) | AI 에이전트 스킬 CLI (JSON 출력, 화면 없음) | diagnose(적대적 검증·시간 순서·반복 엔티티·단일 피처 누수), CV↔LB 기록과 경보, OOF 앙상블, 제출 전 확인 | 별 1, 캐글 전용, 데이콘 언급 없음 | 기능상 높음, 형태가 다름 |
| [kaggle-prep](https://pypi.org/project/kaggle-prep/) | CLI + HTML 리포트 | 타깃 누수·ID형·중복·KS 드리프트 | 별 0, 2026-09 | 중간 |
| [nyaggle](https://github.com/nyanp/nyaggle) | 라이브러리 | AV, OOF 저장, 블렌딩 | 2023 정지 | 중간 |
| [Deepchecks](https://docs.deepchecks.com/stable/tabular/auto_checks/train_test_validation/index.html) | 라이브러리 | 드리프트·누수 검사 | 2024-12 정지 | 중간 |
| [yaEDA](https://github.com/rnascunha/yaEDA) | 라이브러리 | 대회용 EDA, 드리프트 | 별 0, 2026-09 첫 릴리스 | 낮음~중간 |
| [Sweetviz](https://github.com/fbdesignpro/sweetviz), [ydata compare](https://docs.profiling.ydata.ai/latest/features/comparing_datasets/) | HTML 리포트 | 두 데이터 비교 | - | 낮음~중간 |
| [kaggle-mcp](https://github.com/parkseokjune/kaggle-mcp) | MCP 서버 | 점수 조회, 제출 미리보기 | 별 0 | 낮음 |
| [donigian/kaggle-submission-tracker](https://github.com/donigian/kaggle-submission-tracker) | Go REST API | CV/Public/Private 기록 | 2017 방치 | 낮음 |

결론: 여섯 기능(EDA, train/test 차이, 누수·중복, CV·LB 기록, OOF 앙상블, 제출 검증)을 한 로컬 화면에 묶은 도구는 찾지 못했습니다. GUI 도구(Orange, KNIME, Weka, RapidMiner, Exploratory, JASP)는 메모리·규모 한계와 파이썬 생태계 단절로 대회에서 쓰이지 않습니다 ([ML Contests 2024](https://mlcontests.com/state-of-machine-learning-competitions-2024/): 우승 솔루션 79개 중 76개가 파이썬, GBDT 지배).

## 2. 참가자가 반복해서 겪는 불편 (근거)

1. **CV와 Public LB 불일치·셰이크업 (자주)**: [데이콘 405583](https://dacon.io/en/forum/405583), [406653](https://dacon.io/en/forum/406653), [407890](https://dacon.io/en/forum/407890), [코드공유 12288](https://dacon.io/competitions/official/236450/codeshare/12288), [fast.ai](https://forums.fast.ai/t/danger-zone-kaggle-lb-overfitting/7381), [AIcrowd](https://discourse.aicrowd.com/t/do-you-trust-your-leaderboard-score/5850), [DrivenData (OOF로 Public/Private 분할 시뮬레이션)](https://community.drivendata.org/t/sharing-cv-scores-and-lb-scores/8912).
2. **최종 제출 고르기**: [fast.ai](https://forums.fast.ai/t/danger-zone-kaggle-lb-overfitting/7381), **데이콘: 최종 선택 후 새로 제출하면 Public 최고점 파일로 자동 변경** ([412692](https://dacon.io/en/competitions/official/236336/talkboard/412692)), 대회별 선택 개수 상이 ([규칙 236459](https://dacon.io/en/competitions/official/236459/overview/rules)).
3. **train/test 분포 차이 (자주)**: [데이콘 411818](https://dacon.io/en/competitions/official/236258/talkboard/411818), [AV 코드공유 1131](https://dacon.io/en/competitions/official/235614/codeshare/1131), [NVIDIA 그랜드마스터 플레이북](https://developer.nvidia.com/blog/the-kaggle-grandmasters-playbook-7-battle-tested-modeling-techniques-for-tabular-data).
4. **누수 (가끔, 영향 큼)**: 행 순서 누수 [Zindi](https://zindi.world/competitions/geoai-aquaculture-pond-identification-challenge/discussions/33378), 데이콘의 엄격한 참가자 코드 규칙(test로 fit 금지, test 통계 금지 등) [236055](https://dacon.io/en/competitions/official/236055/talkboard/407731).
5. **실험 기록 (자주)**: 메모장·시트 기록의 불편 [velog](https://velog.io/@ththth663/MLflow-%EC%82%B4%ED%8E%B4%EB%B3%B4%EA%B8%B0), [velog 회고](https://velog.io/@idj7183/%ED%94%BC%EB%93%9C%EB%B0%B1-2).
6. **OOF 관리·앙상블 (가끔)**: [velog OOF](https://velog.io/@girae_/%EC%9A%A9%EC%96%B4%EC%82%AC%EC%A0%84-OOFOut-of-Fold).
7. **제출 형식 실수 (자주)**: 컬럼명 [fast.ai](https://forums.fast.ai/t/kaggle-submission-failed/14442), ID 지수 표기 [DrivenData](https://community.drivendata.org/t/submission-error-with-ids/4916), 날짜 형식·파일명 [데이콘 406666](https://dacon.io/en/forum/406666), 인코딩·공백 [데이콘 401193](https://dacon.io/en/competitions/open/235615/talkboard/401193), predict_proba 안내 (Kaggle, 검색 요약).
8. **대용량 CSV 로딩 (데이터 큰 대회)**: [데이콘 695](https://dacon.io/en/competitions/official/235583/codeshare/695), [데이콘 4188](https://dacon.io/en/codeshare/4188).
9. **한글 인코딩 cp949 (한국 특유)**: [데이콘 243750](https://dacon.io/en/competitions/official/235401/talkboard/243750), [velog](https://velog.io/@calico/%ED%95%9C%EA%B5%AD%EC%96%B4-%EC%9D%B8%EC%BD%94%EB%94%A9UTF-8-EUC-KR-CP949).
10. **데이콘 복합 평가식·제출 한도**: [412182 (0.5×(1−AUC)+0.25×Brier+0.25×ECE)](https://dacon.io/en/forum/412182), [405016](https://www.dacon.io/competitions/open/235536/talkboard/405016), [405958](https://dacon.io/en/forum/405958).

## 3. 차별점이 약한 부분 (솔직하게)

- 일반 EDA 리포트·데이터프레임 GUI는 무료 도구가 많습니다(Sweetviz, ydata, D-Tale, PyGWalker).
- 분포 차이·누수 계산 자체는 Deepchecks 등에 이미 있습니다.
- 실험 추적 UI는 MLflow·W&B가 있습니다. 대회용(LB·제출 중심)으로 좁혀야 의미가 있습니다.
- 앙상블 알고리즘은 이미 여러 라이브러리에 있습니다.
- AI 에이전트 흐름(kx, AutoKaggle 등)이 커지고 있어, 사람용 화면과 스크립트·에이전트용 입출력을 같이 제공해야 합니다.
