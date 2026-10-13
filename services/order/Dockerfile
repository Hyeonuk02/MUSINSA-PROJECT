# 빌드 컨텍스트는 services/ (Phase 3.2: 공용 검증 모듈 evidence-collector를 함께 빌드)
#   docker build -f services/order/Dockerfile -t order-app:<tag> services/
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY evidence-collector ./evidence-collector
RUN mvn -q -B -f evidence-collector/pom.xml install -DskipTests
COPY order/pom.xml order/pom.xml
RUN mvn -q -B -f order/pom.xml dependency:go-offline
COPY order/src order/src
RUN mvn -q -B -f order/pom.xml package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/order/target/order-app.jar app.jar
EXPOSE 8080
# JVM 타임존을 UTC로 고정한다. APP_FIXED_CLOCK과 함께 legacy/new의 시각 관련
# 동작이 호스트 환경에 좌우되지 않게 하기 위함이다.
ENTRYPOINT ["java", "-Duser.timezone=UTC", "-jar", "app.jar"]
