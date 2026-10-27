/**
 * Contract Drift Check Script
 *
 * Compares frontend TypeScript types against the frozen OpenAPI contract.
 * Run this to detect any drift between implementation and contract.
 *
 * Usage: node --import tsx scripts/check-contract-drift.ts
 */

import fs from 'fs';
import path from 'path';
import yaml from 'yaml';

/**
 * Parse OpenAPI schema names from YAML
 */
export function parseOpenAPI(filePath: string): string[] {
  const content = fs.readFileSync(filePath, 'utf-8');
  const doc = yaml.parse(content);

  const schemas = doc.components?.schemas;
  if (!schemas) return [];

  return Object.keys(schemas);
}

/**
 * Parse TypeScript interface/type names from api.ts
 */
export function parseTypeScriptTypes(filePath: string): string[] {
  const content = fs.readFileSync(filePath, 'utf-8');
  const typeNames: string[] = [];

  const exportTypeRegex = /export\s+type\s+(\w+)\s*=/g;
  const exportInterfaceRegex = /export\s+interface\s+(\w+)\s*{/g;

  let match;
  while ((match = exportTypeRegex.exec(content)) !== null) {
    typeNames.push(match[1]);
  }
  while ((match = exportInterfaceRegex.exec(content)) !== null) {
    typeNames.push(match[1]);
  }

  return typeNames;
}

/**
 * Main check function
 */
export function checkContractDrift(): boolean {
  const openApiPath = path.join(__dirname, '../docs/contracts/phase2.openapi.yaml');
  const tsTypesPath = path.join(__dirname, '../apps/web/src/types/api.ts');

  console.log('🔍 Checking contract drift...\n');
  console.log(`OpenAPI: ${openApiPath}`);
  console.log(`TypeScript: ${tsTypesPath}\n`);

  const openApiSchemas = parseOpenAPI(openApiPath);
  const tsTypes = parseTypeScriptTypes(tsTypesPath);

  console.log(`OpenAPI schemas (${openApiSchemas.length}):`);
  openApiSchemas.forEach(s => console.log(`  - ${s}`));

  console.log(`\nTypeScript types (${tsTypes.length}):`);
  tsTypes.forEach(t => console.log(`  - ${t}`));

  const missingInTS = openApiSchemas.filter(s => !tsTypes.includes(s));
  const extraInTS = tsTypes.filter(t => !openApiSchemas.includes(t));

  // Types that are expected to be extra (internal/shared types)
  const expectedExtra = new Set([
    'UUID',
    'OnboardingStatus',
    'OrganizationType',
    'MembershipRole',
    'ApiErrorDetail',
    'ApiErrorResponse',
    'HealthResponse',
    'DatabaseHealthResponse',
    'UserUpdateRequest',
    'WorkerProfileCreateRequest',
    'WorkerProfileUpdateRequest',
    'OrganizationCreateRequest',
  ]);

  console.log('\n📋 Drift Report:');

  if (missingInTS.length > 0) {
    console.log('\n❌ In OpenAPI but missing in TypeScript (CRITICAL):');
    missingInTS.forEach(s => console.log(`  - ${s}`));
  } else {
    console.log('\n✅ All OpenAPI schemas present in TypeScript');
  }

  const unexpectedExtra = extraInTS.filter(t => !expectedExtra.has(t));

  if (unexpectedExtra.length > 0) {
    console.log('\n⚠️  Unexpected types in TypeScript (not in OpenAPI and not expected):');
    unexpectedExtra.forEach(t => console.log(`  - ${t}`));
  } else if (extraInTS.length > 0) {
    console.log('\n✅ Extra TypeScript types are expected/internal (enums, requests, etc.)');
    extraInTS.forEach(t => console.log(`  - ${t} (expected)`));
  }

  const criticalIssues = missingInTS.length + unexpectedExtra.length;
  console.log(`\n${criticalIssues === 0 ? '✅' : '❌'} ${criticalIssues} critical issue(s) found`);
  console.log(`  - Missing in TS: ${missingInTS.length}`);
  console.log(`  - Unexpected extra: ${unexpectedExtra.length}`);

  return criticalIssues === 0;
}

/**
 * Run if executed directly
 */
if (import.meta.url === `file://${process.argv[1]}`) {
  const passed = checkContractDrift();
  process.exit(passed ? 0 : 1);
}