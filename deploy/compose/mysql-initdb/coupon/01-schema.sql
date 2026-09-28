-- coupon-service 스키마 (MySQL 8.4) -- S0의 스키마 부분
--
-- 생성: deploy/compose/tools/dump-schema.sh (Hibernate ddl-auto=update 1회 -> mysqldump --no-data)
-- MySQL 이미지가 초기화 시 /docker-entrypoint-initdb.d를 MYSQL_DATABASE(coupon_db)에 실행한다.
-- 앱은 ddl-auto: none이므로 스키마는 이 파일 하나가 소유한다.
-- mysqldump는 테이블을 이름순으로 내보내므로 FK 참조 순서와 다르다. 생성 중에만 FK 검사를 끈다.
SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `coupon_usage` (
  `usage_id` bigint NOT NULL AUTO_INCREMENT,
  `order_id` bigint NOT NULL,
  `used_at` datetime(6) NOT NULL,
  `user_id` bigint NOT NULL,
  `coupon_id` bigint NOT NULL,
  PRIMARY KEY (`usage_id`),
  KEY `FKof9h3rw1vu403j5dbehr45ts2` (`coupon_id`),
  CONSTRAINT `FKof9h3rw1vu403j5dbehr45ts2` FOREIGN KEY (`coupon_id`) REFERENCES `coupons` (`coupon_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `coupons` (
  `coupon_id` bigint NOT NULL AUTO_INCREMENT,
  `code` varchar(255) NOT NULL,
  `discount_type` varchar(255) NOT NULL,
  `discount_value` decimal(38,2) NOT NULL,
  `expiry_date` datetime(6) DEFAULT NULL,
  `max_discount` decimal(38,2) DEFAULT NULL,
  `min_order_value` decimal(38,2) DEFAULT NULL,
  `usage_limit` int DEFAULT NULL,
  PRIMARY KEY (`coupon_id`),
  UNIQUE KEY `UKeplt0kkm9yf2of2lnx6c1oy9b` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET FOREIGN_KEY_CHECKS=1;
