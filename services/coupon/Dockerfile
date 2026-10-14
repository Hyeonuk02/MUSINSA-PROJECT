# 빌드 컨텍스트는 services/ (공용 검증 모듈 evidence-collector를 함께 빌드)
#   docker build -f services/coupon/Dockerfile -t coupon-app:<tag> services/
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY evidence-collector ./evidence-collector
RUN mvn -q -B -f evidence-collector/pom.xml install -DskipTests
COPY coupon/pom.xml coupon/pom.xml
RUN mvn -q -B -f coupon/pom.xml dependency:go-offline
COPY coupon/src coupon/src
RUN mvn -q -B -f coupon/pom.xml package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/coupon/target/coupon-app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-Duser.timezone=UTC", "-jar", "app.jar"]
