import { Container, getRandom } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

const INSTANCE_COUNT = 1;

function presentEnvironment(values) {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => typeof value === "string")
  );
}

export class PinchmealContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
  envVars = presentEnvironment({
    GEMINI_API_KEY: env.GEMINI_API_KEY,
    COGNIFY_API_KEY: env.COGNIFY_API_KEY,
    API_AUTH_TOKEN: env.API_AUTH_TOKEN,
    ENVIRONMENT: "production",
    EXPOSE_DOCS: "false",
    WEB_CONCURRENCY: "1",
    GUNICORN_TIMEOUT: "120"
  });
}

export default {
  async fetch(request, runtimeEnv) {
    const container = await getRandom(runtimeEnv.PINCHMEAL_CONTAINER, INSTANCE_COUNT);
    return container.fetch(request);
  }
};
