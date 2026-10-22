// Offline authoring/SDK validation only: no login, network requests or cloud mutations.
import assert from "node:assert/strict";
import { createRailwayContext, project, validateGraph } from "railway/iac";
import program, { partial } from "./railway.ts";

for (const environment of ["production", "staging"]) {
  const definition = await program(createRailwayContext({ environment, projectName: "test-project" }), project);
  assert.equal(partial, "pasarguard-panel");
  assert.equal(definition.name, "test-project");
  const resources = definition.resources.flat();
  assert.equal(resources.length, 2);
  const panel = resources.find((item) => item.name === "panel");
  const data = resources.find((item) => item.name === "panel-data");
  assert.equal(panel.source.repo, "devv1112/panel");
  assert.equal(panel.source.branch, "arena/263b0995-panel");
  assert.equal(panel.build.builder, "DOCKERFILE");
  assert.equal(panel.deploy.healthcheckPath, "/health");
  assert.equal(panel.deploy.healthcheckTimeout, 120);
  assert.equal(panel.deploy.numReplicas, 1);
  assert.equal(panel.deploy.drainingSeconds, 50);
  assert.equal(panel.deploy.sleepApplication, false);
  assert.equal(panel.deploy.requiredMountPath, "/data");
  assert.deepEqual(panel.variables.PORT, { type: "literal", value: "8080" });
  assert.equal(data.config.sizeMB, 500);
  assert.equal(panel.volumeAttachments["panel-data"].volume, data.address);
  assert.equal(panel.volumeAttachments["panel-data"].mountPath, "/data");
  const graph = { version: 1, project: { name: definition.name }, environments: [{ name: environment }], resources, edges: [] };
  assert.deepEqual(validateGraph(graph), []);
}
console.log("Official Railway SDK: production/staging resource definitions valid (offline; no cloud apply)");
