# PantryAI

> 냉장고에 있는 재료를 다 쓰도록 돕는 1인 가구용 요리·식단 추천 서비스.

혼자 사는 사람은 재료 단위가 자기 몸집보다 커서 재료를 남긴다. 대파는 한 단, 양배추는 한 통으로 팔린다. 같은 재료로 만들 줄 아는 요리가 한두 개뿐이라 질려서 안 먹고 결국 버린다.

PantryAI는 사용자의 냉장고를 기억하고 그 재고를 기준으로 요리를 제안한다. **어려운 부분은 재고를 기억하는 게 아니라 계속 맞게 유지하는 것**이라, 재고 갱신을 별도 작업이 아니라 제품을 쓰는 행위의 부산물로 설계했다.

```
추천  →  만들었는지 확인  →  재고 차감  →  차감 내역 검수
  ↑                                            │
  └────────────────────────────────────────────┘
```

**성공의 정의**: 3주 뒤 사용자가 *"비슷한 식재료로 다양한 음식을 해먹었구나"* 라고 느끼는 것.

## 현재 상태

**기획 단계.** 제품 브리프 완료, 레시피 코퍼스 수집 완료.

| | |
| --- | --- |
| 코퍼스 | 농정원 537건 + 식약처 1,156건 → 이름 기준 고유 **1,661종** |
| 카테고리 | 한식 · 양식 · 중식 · 일식 · 동남아 (5종) |
| 다음 | PRD → 아키텍처 → UX → 에픽·스토리 → 구현 |

## 문서

| 문서 | 내용 |
| --- | --- |
| [제품 브리프](_bmad-output/planning-artifacts/briefs/brief-PantryAI-2026-08-13/brief.md) | 문제·해법·범위·성공 기준 |
| [Addendum](_bmad-output/planning-artifacts/briefs/brief-PantryAI-2026-08-13/addendum.md) | API 규격 · 재료 데이터 상세 · 데이터 소스 배제 근거 |
| [카테고리 매핑](_bmad-output/planning-artifacts/briefs/brief-PantryAI-2026-08-13/recipe-category-mapping.json) | 84건 수동 분류 결과 (자동 분류 정답 세트) |

## 데이터 출처

전부 **이용허락범위 제한 없음** 또는 CC BY-SA로 확인된 공공데이터다.

- [식품의약품안전처 조리식품의 레시피 DB](https://www.data.go.kr/data/15060073/openapi.do)
- [농림수산식품교육문화정보원 레시피 기본정보](https://www.data.go.kr/data/15057205/openapi.do) · [재료정보](https://www.data.go.kr/data/15058981/openapi.do) · [과정정보](https://www.data.go.kr/data/15056535/openapi.do)

라이선스 검증 결과 만개의레시피(CC BY-NC-ND)와 RecipeNLG(비상업 한정)는 배제했다. 배제 근거는 Addendum에 있다.

## 개발 방식

| 단계 | 도구 | 산출물 |
| --- | --- | --- |
| 기획 · 설계 | BMAD | `_bmad-output/` |
| 구현 · 테스트 | superpowers | 코드 + 테스트 (TDD) |

- 작업 단위는 **BMAD 스토리**
- 에픽·스토리 분해가 끝나면 BMAD를 제거하고 산출물을 `docs/`로 옮긴다

## 로컬 설정

```bash
cp .env.example .env    # 공공데이터 인증키 입력
```

`DATA_GO_KR_SERVICE_KEY`는 [공공데이터포털](https://www.data.go.kr/), `FOOD_SAFETY_KOREA_API_KEY`는 [식품안전나라](https://www.foodsafetykorea.go.kr/apiMain.do)에서 발급한다. 두 포털은 인증키를 공유하지 않는다.

## 레포 구조

```
_bmad/          BMAD 설치 (설정 · 모듈)
_bmad-output/   기획 산출물 — 프로젝트의 청사진
.claude/skills/ BMAD가 렌더링한 스킬
data/raw/       수집한 원천 데이터 (gitignored — 공공 API에서 재생성 가능)
docs/           영구 문서
```
