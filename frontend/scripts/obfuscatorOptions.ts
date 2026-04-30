export function createProductionObfuscatorOptions() {
  return {
    identifierNamesGenerator: "hexadecimal" as const,
    renameGlobals: false, // 不重命名全局：避免破坏 React 运行时

    sourceMap: false,

    stringArray: false,

    splitStrings: false, // 关闭：避免破坏 EventSource URL 构造

    controlFlowFlattening: false, // 关闭：构建时间翻倍，SSE 处理器有风险
    selfDefending: false, // 关闭：与 React 不兼容
    debugProtection: false, // 关闭：会破坏 SSE DevTools 调试

    disableConsoleOutput: true,
    deadCodeInjection: false, // 关闭：显著增加包体积
    unicodeEscapeSequence: false, // 关闭：大幅增加体积

    target: "browser" as const,
  };
}
