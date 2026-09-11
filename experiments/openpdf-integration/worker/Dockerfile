# Build with repository root as context. This image is an unshipped isolation proof only.
FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY experiments/openpdf-integration/pom.xml ./pom.xml
COPY experiments/openpdf-integration/src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre
RUN groupadd --gid 10001 claros-worker \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin claros-worker \
    && mkdir -p /opt/claros/fonts /job /tmp/claros \
    && chown 10001:10001 /job /tmp/claros
COPY --from=build --chown=0:0 \
    /build/target/openpdf-integration-0.1.0-SNAPSHOT-all.jar /opt/claros/worker.jar
COPY --chown=0:0 assets/fonts/noto-sans/NotoSans-Regular.ttf \
    /opt/claros/fonts/NotoSans-Regular.ttf
USER 10001:10001
WORKDIR /job
ENTRYPOINT ["java","-Djava.awt.headless=true","-Djava.io.tmpdir=/tmp/claros","-Xms16m","-Xmx192m","-jar","/opt/claros/worker.jar","--job-dir","/job","--font-dir","/opt/claros/fonts"]
