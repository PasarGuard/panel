// DOM suites mock Vite-only modules. Separate processes prevent mock/global leakage.
const suites = [
  'src/features/client-settings/workspace-model.test.ts',
  'src/features/client-settings/forms/native-configuration.test.ts',
  'src/features/client-settings/components/native-configuration-editor.test.tsx',
  'src/features/client-settings/workspace-page.test.tsx',
  'src/features/client-settings/client-settings-locales.test.ts',
  'src/features/templates/forms/subscription-profile-form.test.ts',
  'src/features/templates/components/subscription-profile-locales.test.ts',
  'src/features/subscriptions/components/client-routing-legacy-rules.test.ts',
  'src/utils/client-workspace-rbac.test.ts',
  'src/features/hosts/forms/host-form.test.ts',
  'src/features/subscriptions/components/subscription-settings-schema.test.ts',
  'src/features/templates/forms/client-template-form.test.ts',
]
for (const suite of suites) {
  const result = Bun.spawnSync([process.execPath, 'test', suite], { stdout: 'inherit', stderr: 'inherit' })
  if (result.exitCode !== 0) process.exit(result.exitCode)
}
