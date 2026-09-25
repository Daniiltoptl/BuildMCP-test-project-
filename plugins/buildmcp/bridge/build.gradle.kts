plugins {
    java
}

group = "dev.buildmcp"
version = providers.gradleProperty("bridgeVersion").getOrElse("0.1.0")

// Paper API to compile against. The plugin only uses API that is stable across 1.21.x,
// CI builds once and runs the jar on several server versions.
val paperApi = providers.gradleProperty("paperApi").getOrElse("1.21.1-R0.1-SNAPSHOT")

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    compileOnly("io.papermc.paper:paper-api:$paperApi")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(21)
    options.compilerArgs.add("-Xlint:all,-deprecation,-processing,-serial,-classfile,-options")
}

tasks.processResources {
    val props = mapOf("version" to project.version)
    inputs.properties(props)
    filesMatching("plugin.yml") { expand(props) }
}

tasks.jar {
    archiveFileName.set("BuildBridge-${project.version}.jar")
}
