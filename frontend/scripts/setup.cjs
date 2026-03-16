#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const dockerSetupScript = path.join(frontendDir, 'scripts', 'run-in-dev-container.sh');
const envExamplePath = path.join(frontendDir, '.env.example');
const envPath = path.join(frontendDir, '.env');

function run(command, args, cwd = frontendDir) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed with exit code ${result.status ?? 'unknown'}`);
  }
}

function hasCommand(command, args = ['--version']) {
  const result = spawnSync(command, args, { stdio: 'ignore' });
  return result.status === 0;
}

function ensureEnvFile() {
  if (!fs.existsSync(envPath) && fs.existsSync(envExamplePath)) {
    fs.copyFileSync(envExamplePath, envPath);
    console.log('已从 .env.example 创建 frontend/.env');
  }
}

function isNodeVersionSupported() {
  const [major = '0', minor = '0'] = process.versions.node.split('.');
  return Number(major) > 20 || (Number(major) === 20 && Number(minor) >= 6);
}

function ensurePnpm() {
  if (hasCommand('pnpm')) return true;
  if (!hasCommand('corepack')) return false;

  const enableResult = spawnSync('corepack', ['enable'], { stdio: 'inherit' });
  if (enableResult.status !== 0) return false;

  const prepareResult = spawnSync('corepack', ['prepare', 'pnpm@9.15.4', '--activate'], {
    stdio: 'inherit',
  });
  return prepareResult.status === 0 && hasCommand('pnpm');
}

function main() {
  ensureEnvFile();

  const localSupported = isNodeVersionSupported() && ensurePnpm();
  if (localSupported) {
    console.log('使用本机 Node + pnpm 安装前端依赖');
    run('pnpm', ['install', '--no-frozen-lockfile']);
    return;
  }

  console.log('本机前端工具链不可用，切换到 Docker 前端环境完成安装');
  run('bash', [dockerSetupScript, 'pnpm', 'install', '--no-frozen-lockfile'], repoRoot);
}

main();
