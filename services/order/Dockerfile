FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/target/order-app.jar app.jar
EXPOSE 8080
# JVM 타임존을 UTC로 고정한다. APP_FIXED_CLOCK과 함께 legacy/new의 시각 관련
# 동작이 호스트 환경에 좌우되지 않게 하기 위함이다.
ENTRYPOINT ["java", "-Duser.timezone=UTC", "-jar", "app.jar"]
