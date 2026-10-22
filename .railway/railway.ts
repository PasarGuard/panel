import { defineRailway, github, project, service, volume } from "railway/iac";

// Partial ownership protects unrelated resources in the selected environment.
export const partial = "pasarguard-panel";

export default defineRailway((ctx) => {
  // 500 MB stays within the documented 0.5 GB Free/Trial volume ceiling.
  const data = volume("panel-data", { sizeMB: 500 });
  const panel = service("panel", {
    source: github("devv1112/panel", { branch: "arena/263b0995-panel" }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    replicas: 1,
    healthcheck: "/health",
    healthcheckTimeout: 120,
    deploy: {
      drainingSeconds: 50,
      overlapSeconds: 0,
      requiredMountPath: "/data",
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      sleepApplication: false,
    },
    volumeMounts: { "/data": data },
    env: { PORT: "8080" },
  });
  return project(ctx.projectName || "pasarguard-panel", { resources: [panel, data] });
});
