# Prince Mart 결함과 정상 변경 New 버전 (5단계)

팀원 `fault/F<n>`과 같은 방식이다. 기준선(prince-mart 브랜치) 위에 서비스 코드만 바꾼 커밋 1개를 둔 `fault/PF<n>` 브랜치를 만들고,
그 브랜치에서 바꾼 서비스 이미지 하나만 `prince-mart/<svc>-service:PF<n>`으로 빌드해 pm-new에 올린다.

| 파일 | 내용 |
|---|---|
| `make_patches.py` | 패치 생성기. branch-park의 PF 편집을 지금 코드에 맞춰 옮겼다. `--check`는 지금 패치가 생성 결과와 같은지 확인 |
| `PF<n>-<svc>.patch` | 저장소 루트 기준 패치(10개). PF6은 payment Jackson 2 -> 3 전환 |
| `fault-expectations.json` | 기대 판정 사전 등록(정답 `targets`, 예상 엔진 판정 `expectedEngine`, pair 키는 팀원 엔진 키) |
| `branch-park/` | branch-park(e2da8be)의 `fault-expectations.json`, `fault-expectations-amendments.json`, `fault-catalog.md` 원본 그대로 |

| PF | 서비스 | 종류 | 내용 |
|---|---|---|---|
| PF1 | payment | 진짜 결함 | PG 주문 생성 2번 호출 |
| PF2 | payment | 진짜 결함 | PaymentCompleted 발행 누락 |
| PF3 | order | 진짜 결함 | 장바구니 비우기와 재고 차감 순서 뒤바뀜 |
| PF4 | order | 진짜 결함 | 취소 시 재고 복구 호출 누락 |
| PF5 | order | 정상 리팩터링 | 취소 조회 fetch join(SELECT 2 -> 1) |
| PF6 | payment | 정상 변경 | Jackson 2 ObjectMapper -> Jackson 3 JsonMapper |
| PF7 | order | 승인된 개선 | B4 수정(취소 주문은 결제 완료로 확정하지 않음) |
| PF8 | order | 성능 결함 | 내 주문 조회 N+1 |
| PF9 | order | 승인된 개선 | 재확정 멱등 |
| PF10 | order | 승인된 개선 | B1 수정(쿠폰 사용 기록을 커밋 뒤로) |

## 브랜치 만들기 (결함마다)

```bash
git switch prince-mart
git switch -c fault/PF1
git apply tracks/prince-mart/tools/faults/PF1-payment.patch
git commit -am "prince-mart: PF1 결제 처리에서 PG 주문 생성을 2번 호출(진짜 결함)"
git switch prince-mart
```

## 판정 run (6단계, 사전 등록 커밋 뒤)

```bash
git switch fault/PF1
docker build -f tracks/prince-mart/app/payment-service/DockerFile -t prince-mart/payment-service:PF1 .
kind load docker-image prince-mart/payment-service:PF1 --name musinsa-phase1
git switch prince-mart
# pm-new의 그 서비스만 교체하고 EVIDENCE_VERSION=PF1 (new overlay의 images, 스택 patch)
tracks/prince-mart/tools/run-pm.sh --run-id pf1 --iterations 3
.venv/bin/python engine/verdict.py --run runs/pf1-1 --rules tracks/prince-mart/tools/rules
```

판정에 쓰는 규칙은 `fault-expectations.json`의 `judge`에 있다(기본, PF8 max_selects 선언판, PF7 사전 승인 규칙).
