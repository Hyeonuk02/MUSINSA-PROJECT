-- payment-service 스키마 (MySQL 8.4) -- S0의 스키마 부분
--
-- 생성: deploy/compose/tools/dump-schema.sh (Hibernate ddl-auto=update 1회 -> mysqldump --no-data)
-- MySQL 이미지가 초기화 시 /docker-entrypoint-initdb.d를 MYSQL_DATABASE(payment_db)에 실행한다.
-- 앱은 ddl-auto: none이므로 스키마는 이 파일 하나가 소유한다.
-- mysqldump는 테이블을 이름순으로 내보내므로 FK 참조 순서와 다르다. 생성 중에만 FK 검사를 끈다.
SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `payments` (
  `payment_id` bigint NOT NULL AUTO_INCREMENT,
  `amount` decimal(38,2) DEFAULT NULL,
  `created_at` datetime(6) DEFAULT NULL,
  `currency` varchar(255) DEFAULT NULL,
  `order_id` bigint NOT NULL,
  `payment_method` varchar(255) NOT NULL,
  `status` varchar(255) DEFAULT NULL,
  `transaction_id` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`payment_id`),
  UNIQUE KEY `UKlryndveuwa4k5qthti0pkmtlx` (`transaction_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `refunds` (
  `refund_id` bigint NOT NULL AUTO_INCREMENT,
  `amount` decimal(38,2) DEFAULT NULL,
  `created_at` datetime(6) DEFAULT NULL,
  `reason` varchar(255) DEFAULT NULL,
  `status` varchar(255) DEFAULT NULL,
  `payment_id` bigint DEFAULT NULL,
  PRIMARY KEY (`refund_id`),
  KEY `FKpt9ic0j1y6xwlej99wnynvnpy` (`payment_id`),
  CONSTRAINT `FKpt9ic0j1y6xwlej99wnynvnpy` FOREIGN KEY (`payment_id`) REFERENCES `payments` (`payment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET FOREIGN_KEY_CHECKS=1;
