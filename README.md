# PantryAI

> 아직 제품 정의 단계입니다. 제품 브리프 작성 후 이 문서를 갱신합니다.

## 개발 방식

| 단계 | 도구 | 산출물 |
| --- | --- | --- |
| 기획 · 설계 | BMAD | `_bmad-output/` (브리프, PRD, 아키텍처, 에픽/스토리) |
| 구현 · 테스트 | superpowers | 코드 + 테스트 (TDD 루프) |
| E2E 테스트 | BMAD (`bmad-qa-generate-e2e-tests`) | 스토리 인수 조건 기반 시나리오 |

- 작업 단위는 **BMAD 스토리**입니다.
- 구현은 스토리 단위 브랜치에서 superpowers TDD 루프로 진행합니다.
- 에이전트가 따라야 할 프로젝트 규칙은 `AGENTS.md`에 있습니다 (아키텍처 확정 후 생성).

## 레포 구조

```
_bmad/          BMAD 설치 (설정 · 모듈)
_bmad-output/   BMAD 산출물 — 프로젝트의 청사진
.claude/skills/ BMAD가 렌더링한 스킬
```
