# 동적 Call Graph 맵 (Phase 4.1)

> `scoping/map_report.py`가 `scoping/map.json`에서 생성한다. 손으로 고치지 않는다. 정본 입력 p36-base-1, p36-base-2, p36-base-3 (Legacy 레코드, corpus-v2.1), 맵 본문 `sha256:2c968eee26ce569aa504a1c415ba775e2af73d7b73300a6fe5b0eec89ae6668e`.

맵은 corpus가 실행한 경로만 안다. 매칭은 클래스 단위, 정본은 요청 단위(D23), 엔드포인트 표는 요약이며 corpus 재생의 선택에는 쓰지 않는다.

## 커버리지

엔드포인트 8/8.

| 소스 | 빈 클래스 | 맵 등장 | 미관측 빈 | 이유 |
|---|---|---|---|---|
| `phase3.3-base` | 11 | 10 | RequestLogFilter | AOP 포인트컷 제외 — !within(jakarta.servlet.Filter+) (EvidenceAutoConfiguration.callTreeExpression) |
| `phase3.5-v1.4` | 11 | 10 | RequestLogFilter | AOP 포인트컷 제외 — !within(jakarta.servlet.Filter+) (EvidenceAutoConfiguration.callTreeExpression) |

빈이 아니라 AOP가 보지 못하는 클래스(변경되면 폐포 대상): `coupon.ClockConfig`(config), `coupon.Coupon`(entity), `coupon.CouponApplication`(main), `coupon.CouponView`(plain), `coupon.KafkaConfig`(config), `order.ClockConfig`(config), `order.Order`(entity), `order.OrderApplication`(main), `order.OrderItem`(entity), `order.OrderPaid`(plain), `order.OrderView`(plain), `order.requestlog.CachedBodyRequest`(plain).

## 엔드포인트 → 클래스 (요약)

| 엔드포인트 | 진입 요청 | 자식 홉 요청 | 세션 | 클래스 |
|---|---|---|---|---|
| consume.order.paid | 0 | 7 | 7 | CouponRepository, CouponService, OrderPaidListener |
| coupon.create | 6 | 0 | 6 | CouponController, CouponRepository, CouponService |
| coupon.get | 6 | 0 | 3 | CouponController, CouponRepository, CouponService |
| coupon.use | 4 | 5 | 6 | CouponController, CouponRepository, CouponService |
| order.cancel | 1 | 0 | 1 | OrderController, OrderRepository, OrderService |
| order.create | 10 | 0 | 9 | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| order.get | 13 | 0 | 9 | OrderController, OrderRepository, OrderService |
| order.pay | 8 | 0 | 7 | CouponRepository, CouponService, OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |

## 클래스 → 요청

| 클래스 | 실행 요청 | 세션 | 엔드포인트 |
|---|---|---|---|
| `poc.coupon.CouponController` | 21 | 6 (S004, S005, S006, S007, S008, S010) | coupon.create, coupon.get, coupon.use, order.create |
| `poc.coupon.CouponRepository` | 24 | 6 (S004, S005, S006, S007, S008, S010) | consume.order.paid, coupon.create, coupon.get, coupon.use, order.create, order.pay |
| `poc.coupon.CouponService` | 24 | 6 (S004, S005, S006, S007, S008, S010) | consume.order.paid, coupon.create, coupon.get, coupon.use, order.create, order.pay |
| `poc.coupon.OrderPaidListener` | 7 | 7 (S001, S002, S003, S006, S007, S009, S010) | consume.order.paid, order.pay |
| `poc.order.CouponClient` | 5 | 4 (S006, S007, S008, S010) | order.create |
| `poc.order.OrderController` | 32 | 9 (S001, S002, S003, S006, S007, S008, S009, S010, S011) | order.cancel, order.create, order.get, order.pay |
| `poc.order.OrderEventPublisher` | 7 | 7 (S001, S002, S003, S006, S007, S009, S010) | order.pay |
| `poc.order.OrderRepository` | 32 | 9 (S001, S002, S003, S006, S007, S008, S009, S010, S011) | order.cancel, order.create, order.get, order.pay |
| `poc.order.OrderService` | 32 | 9 (S001, S002, S003, S006, S007, S008, S009, S010, S011) | order.cancel, order.create, order.get, order.pay |
| `poc.order.PaymentGatewayClient` | 7 | 7 (S001, S002, S003, S006, S007, S009, S010) | order.pay |

## 서비스 간 간선

| 요청 | 세션 | 진입 엔드포인트 | 홉 | 종류 | 실행된 클래스 |
|---|---|---|---|---|---|
| R000003 | S001 | order.pay | `0.e1` | Kafka | OrderPaidListener |
| R000007 | S002 | order.pay | `0.e1` | Kafka | OrderPaidListener |
| R000012 | S003 | order.pay | `0.e1` | Kafka | OrderPaidListener |
| R000027 | S006 | order.create | `0.h1` | HTTP | CouponController, CouponRepository, CouponService |
| R000029 | S006 | order.pay | `0.e1` | Kafka | CouponRepository, CouponService, OrderPaidListener |
| R000032 | S007 | order.create | `0.h1` | HTTP | CouponController, CouponRepository, CouponService |
| R000033 | S007 | order.pay | `0.e1` | Kafka | CouponRepository, CouponService, OrderPaidListener |
| R000036 | S008 | order.create | `0.h1` | HTTP | CouponController, CouponRepository, CouponService |
| R000037 | S008 | order.create | `0.h1` | HTTP | CouponController, CouponRepository, CouponService |
| R000041 | S009 | order.pay | `0.e1` | Kafka | OrderPaidListener |
| R000044 | S010 | order.create | `0.h1` | HTTP | CouponController, CouponRepository, CouponService |
| R000045 | S010 | order.pay | `0.e1` | Kafka | CouponRepository, CouponService, OrderPaidListener |

## 요청 → 클래스 (정본)

| 요청 | 세션 | 엔드포인트 | 홉 | 클래스(모든 홉 합산) |
|---|---|---|---|---|
| R000001 | S001 | order.create | `0` | OrderController, OrderRepository, OrderService |
| R000002 | S001 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000003 | S001 | order.pay | `0`, `0.e1` | OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000004 | S001 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000005 | S002 | order.create | `0` | OrderController, OrderRepository, OrderService |
| R000006 | S002 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000007 | S002 | order.pay | `0`, `0.e1` | OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000008 | S002 | order.pay | `0` | OrderController, OrderRepository, OrderService |
| R000009 | S002 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000010 | S003 | order.create | `0` | OrderController, OrderRepository, OrderService |
| R000011 | S003 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000012 | S003 | order.pay | `0`, `0.e1` | OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000013 | S003 | order.cancel | `0` | OrderController, OrderRepository, OrderService |
| R000014 | S003 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000015 | S004 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000016 | S004 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000017 | S004 | coupon.use | `0` | CouponController, CouponRepository, CouponService |
| R000018 | S004 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000019 | S004 | coupon.use | `0` | CouponController, CouponRepository, CouponService |
| R000020 | S004 | coupon.use | `0` | CouponController, CouponRepository, CouponService |
| R000021 | S005 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000022 | S005 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000023 | S005 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000024 | S005 | coupon.use | `0` | CouponController, CouponRepository, CouponService |
| R000025 | S005 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000026 | S006 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000027 | S006 | order.create | `0`, `0.h1` | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| R000028 | S006 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000029 | S006 | order.pay | `0`, `0.e1` | CouponRepository, CouponService, OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000030 | S006 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000031 | S007 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000032 | S007 | order.create | `0`, `0.h1` | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| R000033 | S007 | order.pay | `0`, `0.e1` | CouponRepository, CouponService, OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000034 | S007 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000035 | S008 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000036 | S008 | order.create | `0`, `0.h1` | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| R000037 | S008 | order.create | `0`, `0.h1` | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| R000038 | S008 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000039 | S008 | coupon.get | `0` | CouponController, CouponRepository, CouponService |
| R000040 | S009 | order.create | `0` | OrderController, OrderRepository, OrderService |
| R000041 | S009 | order.pay | `0`, `0.e1` | OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000042 | S009 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000043 | S010 | coupon.create | `0` | CouponController, CouponRepository, CouponService |
| R000044 | S010 | order.create | `0`, `0.h1` | CouponClient, CouponController, CouponRepository, CouponService, OrderController, OrderRepository, OrderService |
| R000045 | S010 | order.pay | `0`, `0.e1` | CouponRepository, CouponService, OrderController, OrderEventPublisher, OrderPaidListener, OrderRepository, OrderService, PaymentGatewayClient |
| R000046 | S010 | order.get | `0` | OrderController, OrderRepository, OrderService |
| R000047 | S011 | order.create | `0` | OrderController, OrderRepository, OrderService |
| R000048 | S011 | order.get | `0` | OrderController, OrderRepository, OrderService |
