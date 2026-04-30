
import { useState, useEffect, useRef, useCallback } from "react";
import { Shield, Zap } from "lucide-react";
import { ARGUS_LOGO_SRC } from "@/shared/branding/useLogoVariant";

interface SplashScreenProps {
  onComplete: () => void;
}

const BOOT_SEQUENCE = [
  { text: "[INIT] Loading Argus Core...", delay: 0, type: 'init' },
  { text: "[SCAN] Neural Analysis Engine v3.0", delay: 200, type: 'scan' },
  { text: "[LOAD] Vulnerability Pattern Database", delay: 400, type: 'load' },
  { text: "[SYNC] Agent Orchestration Module", delay: 600, type: 'sync' },
  { text: "[READY] System Online", delay: 800, type: 'ready' },
];

const COMMANDS: Record<string, { action: string; output?: string }> = {
  audit: { action: "start", output: "Initializing scan configuration..." },
  start: { action: "start", output: "Initializing scan configuration..." },
  scan: { action: "start", output: "Initializing scan configuration..." },
  help: { action: "help" },
  clear: { action: "clear" },
};

const HELP_TEXT = `
Available commands:
  scan, start  - Start a new security scan
  help                - Show this help message
  clear               - Clear terminal

Type 'scan' to begin a new security scan.
`;

export function SplashScreen({ onComplete }: SplashScreenProps) {
  const [bootLogs, setBootLogs] = useState<string[]>([]);
  const [showLogo, setShowLogo] = useState(false);
  const [bootComplete, setBootComplete] = useState(false);
  const [commandHistory, setCommandHistory] = useState<Array<{ input: string; output?: string; isError?: boolean }>>([]);
  const [currentInput, setCurrentInput] = useState("");
  const [cursorBlink, setCursorBlink] = useState(true);

  const inputRef = useRef<HTMLInputElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    setTimeout(() => setShowLogo(true), 100);

    BOOT_SEQUENCE.forEach(({ text, delay }) => {
      setTimeout(() => {
        setBootLogs(prev => [...prev, text]);
      }, delay + 400);
    });

    setTimeout(() => setBootComplete(true), 1200);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => setCursorBlink(b => !b), 530);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [bootLogs, commandHistory]);

  useEffect(() => {
    if (bootComplete && inputRef.current) {
      inputRef.current.focus();
    }
  }, [bootComplete]);

  const executeCommand = useCallback((cmd: string) => {
    const trimmedCmd = cmd.trim().toLowerCase();

    if (!trimmedCmd) return;

    const command = COMMANDS[trimmedCmd];

    if (!command) {
      setCommandHistory(prev => [...prev, {
        input: cmd,
        output: `Command not found: ${trimmedCmd}. Type 'help' for available commands.`,
        isError: true
      }]);
      return;
    }

    switch (command.action) {
      case "start":
        setCommandHistory(prev => [...prev, {
          input: cmd,
          output: command.output
        }]);
        setTimeout(() => {
          onCompleteRef.current();
        }, 500);
        break;

      case "help":
        setCommandHistory(prev => [...prev, {
          input: cmd,
          output: HELP_TEXT
        }]);
        break;

      case "clear":
        setCommandHistory([]);
        setBootLogs([]);
        break;
    }
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      executeCommand(currentInput);
      setCurrentInput("");
    }
  };

  const handleTerminalClick = () => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  return (
    <div className="h-screen bg-gray-100 dark:bg-black flex flex-col overflow-hidden relative cyber-splash">
      {/* Gradient background - light/dark adaptive */}
      <div className="absolute inset-0 bg-gradient-to-br from-gray-50 via-gray-100 to-gray-200 dark:from-black dark:via-gray-950 dark:to-black pointer-events-none" />

      {/* Animated cyber grid - adaptive opacity */}
      <div className="absolute inset-0 cyber-grid opacity-20 dark:opacity-30 pointer-events-none" />

      {/* Horizontal scan line animation - dark mode only */}
      <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden hidden dark:block">
        <div className="scan-line" />
      </div>

      {/* CRT screen effect - dark mode only */}
      <div className="absolute inset-0 pointer-events-none z-10 crt-effect hidden dark:block" />

      {/* Glitch overlay - dark mode only */}
      <div className="absolute inset-0 pointer-events-none z-15 glitch-overlay hidden dark:block" />

      {/* Vignette effect - light mode only */}
      <div
        className="absolute inset-0 pointer-events-none z-10 dark:hidden"
        style={{
          background: "radial-gradient(ellipse at center, transparent 0%, transparent 50%, rgba(0,0,0,0.15) 100%)",
        }}
      />
      {/* Vignette effect - dark mode only */}
      <div
        className="absolute inset-0 pointer-events-none z-10 hidden dark:block"
        style={{
          background: "radial-gradient(ellipse at center, transparent 0%, transparent 40%, rgba(0,0,0,0.7) 100%)",
        }}
      />

      {/* Animated data streams - dark mode only */}
      <div className="hidden dark:block">
        <div className="absolute left-4 top-0 bottom-0 w-px overflow-hidden pointer-events-none z-20">
          <div className="data-stream" />
        </div>
        <div className="absolute left-8 top-0 bottom-0 w-px overflow-hidden pointer-events-none z-20">
          <div className="data-stream" style={{ animationDelay: '0.5s' }} />
        </div>
        <div className="absolute right-4 top-0 bottom-0 w-px overflow-hidden pointer-events-none z-20">
          <div className="data-stream" style={{ animationDelay: '1s' }} />
        </div>
        <div className="absolute right-8 top-0 bottom-0 w-px overflow-hidden pointer-events-none z-20">
          <div className="data-stream" style={{ animationDelay: '1.5s' }} />
        </div>
      </div>

      {/* Floating hex codes - dark mode only */}
      <div className="absolute inset-0 pointer-events-none z-5 overflow-hidden hidden dark:block">
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="hex-float text-primary/20 text-xs font-mono"
            style={{
              left: `${10 + i * 12}%`,
              animationDelay: `${i * 0.7}s`,
            }}
          >
            {Math.random().toString(16).substr(2, 8).toUpperCase()}
          </div>
        ))}
      </div>


      {/* Geometric accent lines - adaptive */}
      <div className="absolute top-0 left-0 w-32 dark:w-48 h-px bg-gradient-to-r from-primary/60 dark:from-primary via-primary/30 dark:via-primary/50 to-transparent pointer-events-none z-30" />
      <div className="absolute top-0 left-0 w-px h-32 dark:h-48 bg-gradient-to-b from-primary/60 dark:from-primary via-primary/30 dark:via-primary/50 to-transparent pointer-events-none z-30" />
      <div className="absolute bottom-0 right-0 w-32 dark:w-48 h-px bg-gradient-to-l from-primary/60 dark:from-primary via-primary/30 dark:via-primary/50 to-transparent pointer-events-none z-30" />
      <div className="absolute bottom-0 right-0 w-px h-32 dark:h-48 bg-gradient-to-t from-primary/60 dark:from-primary via-primary/30 dark:via-primary/50 to-transparent pointer-events-none z-30" />

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center p-4 relative z-30">
        <div className="w-full max-w-2xl">
          {/* Logo with adaptive styling */}
          <div className={`text-center mb-10 transition-all duration-1000 ${showLogo ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-8"}`}>
            <div className="relative inline-flex h-32 w-32 items-center justify-center rounded-[2rem] border border-primary/40 bg-primary/10 shadow-[0_0_45px_rgba(255,107,44,0.35)] sm:h-40 sm:w-40">
              <img
                src={ARGUS_LOGO_SRC}
                alt="Argus"
                className="h-24 w-24 object-contain sm:h-32 sm:w-32"
              />
            </div>
            {/* Subtitle - adaptive styling */}
            <div className="flex items-center justify-center gap-3 text-gray-500 dark:text-gray-400 text-sm tracking-[0.3em] uppercase mt-4">
              <div className="w-12 h-px bg-gradient-to-r from-transparent via-primary/40 dark:via-cyan-500/50 to-transparent" />
              <Shield className="w-4 h-4 text-primary/70 dark:text-cyan-500/70" />
              <span className="dark:cyber-text">Autonomous Security Agent</span>
              <Shield className="w-4 h-4 text-primary/70 dark:text-cyan-500/70" />
              <div className="w-12 h-px bg-gradient-to-r from-transparent via-primary/40 dark:via-cyan-500/50 to-transparent" />
            </div>
            {/* Version tag */}
            <div className="mt-2 text-[10px] font-mono text-primary/50 tracking-widest">
              [ v3.0.0 // NEURAL_CORE ]
            </div>
          </div>

          {/* Terminal window - adaptive styling */}
          <div
            className="relative rounded-xl overflow-hidden bg-white dark:bg-transparent border border-gray-200 dark:border-transparent shadow-xl dark:shadow-none"
            onClick={handleTerminalClick}
          >
            {/* Terminal border glow - dark mode only */}
            <div className="absolute inset-0 rounded-xl border border-primary/30 pointer-events-none hidden dark:block" />
            <div className="absolute inset-0 rounded-xl shadow-[0_0_30px_rgba(255,107,44,0.2),inset_0_0_30px_rgba(0,0,0,0.5)] pointer-events-none hidden dark:block" />

            {/* Terminal header - adaptive */}
            <div className="relative flex items-center gap-3 px-4 py-2.5 bg-gray-100 dark:bg-gray-950 border-b border-gray-200 dark:border-primary/20">
              {/* Window dots */}
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-400 dark:bg-red-500 dark:shadow-[0_0_10px_rgba(239,68,68,0.8)]" />
                <div className="w-3 h-3 rounded-full bg-yellow-400 dark:bg-yellow-500 dark:shadow-[0_0_10px_rgba(234,179,8,0.8)]" />
                <div className="w-3 h-3 rounded-full bg-green-400 dark:bg-green-500 dark:shadow-[0_0_10px_rgba(34,197,94,0.8)]" />
              </div>
              {/* Terminal title */}
              <div className="flex-1 flex items-center justify-center gap-2">
                <span className="text-primary/60 text-xs">▶</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 font-mono tracking-[0.15em] uppercase">
                  root@Argus:~#
                </span>
                <span className="w-2 h-4 bg-primary/80 animate-pulse" />
              </div>
              {/* Status indicator */}
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse dark:shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
                <span className="text-[10px] text-emerald-600 dark:text-emerald-500/80 font-mono">LIVE</span>
              </div>
            </div>

            {/* Terminal content - adaptive */}
            <div
              ref={terminalRef}
              className="relative p-5 font-mono text-sm h-80 overflow-y-auto custom-scrollbar bg-gray-50 dark:bg-gray-950/95"
            >
              {/* Boot logs - adaptive styling */}
              {bootLogs.map((log, i) => (
                <div
                  key={`boot-${i}`}
                  className={`mb-2 flex items-center gap-2 ${
                    log.includes("[READY]") ? "text-emerald-600 dark:text-emerald-400" :
                    log.includes("[INIT]") ? "text-primary" :
                    log.includes("[SCAN]") ? "text-violet-600 dark:text-violet-400" :
                    log.includes("[LOAD]") ? "text-amber-600 dark:text-amber-400" :
                    log.includes("[SYNC]") ? "text-cyan-600 dark:text-cyan-400" :
                    "text-gray-500"
                  }`}
                  style={{
                    animation: "fadeSlideIn 0.3s ease-out",
                    animationFillMode: "both",
                    animationDelay: `${i * 0.08}s`
                  }}
                >
                  <span className="text-emerald-600 dark:text-emerald-500/60">$</span>
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    log.includes("[READY]") ? "bg-emerald-500 dark:shadow-[0_0_8px_rgba(52,211,153,0.8)]" :
                    log.includes("[INIT]") ? "bg-primary dark:shadow-[0_0_8px_rgba(255,107,44,0.8)]" :
                    log.includes("[SCAN]") ? "bg-violet-500 dark:shadow-[0_0_8px_rgba(167,139,250,0.8)]" :
                    log.includes("[LOAD]") ? "bg-amber-500 dark:shadow-[0_0_8px_rgba(251,191,36,0.8)]" :
                    log.includes("[SYNC]") ? "bg-cyan-500 dark:shadow-[0_0_8px_rgba(34,211,238,0.8)]" :
                    "bg-gray-400 dark:bg-gray-600"
                  }`} />
                  <span>{log}</span>
                </div>
              ))}

              {/* Welcome message - adaptive */}
              {bootComplete && (
                <div className="mt-5 mb-4 pt-4 border-t border-gray-200 dark:border-primary/20">
                  <div className="flex items-center gap-2 text-primary mb-2">
                    <Zap className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <span className="font-semibold text-cyan-600 dark:text-cyan-400">// SYSTEM READY</span>
                  </div>
                  <div className="text-gray-600 dark:text-gray-400 text-sm pl-6">
                    Execute <span className="text-emerald-600 dark:text-emerald-400 font-bold px-2 py-0.5 bg-emerald-500/10 dark:bg-emerald-500/20 border border-emerald-500/30 rounded">'scan'</span> to initialize security scan protocol
                  </div>
                  <div className="text-gray-400 dark:text-gray-600 text-xs pl-6 mt-1">
                    [ Type 'help' for available commands ]
                  </div>
                </div>
              )}

              {/* Command history */}
              {commandHistory.map((entry, i) => (
                <div key={`cmd-${i}`} className="mb-2">
                  <div className="flex items-center gap-2 text-foreground">
                    <span className="text-emerald-500">$</span>
                    <span>{entry.input}</span>
                  </div>
                  {entry.output && (
                    <div className={`ml-4 mt-1 whitespace-pre-wrap text-xs ${
                      entry.isError ? "text-red-400" : "text-muted-foreground"
                    }`}>
                      {entry.output}
                    </div>
                  )}
                </div>
              ))}

              {/* Current input line */}
              {bootComplete && (
                <div className="flex items-center gap-2 text-foreground">
                  <span className="text-emerald-500">$</span>
                  <div className="flex-1 relative">
                    <input
                      ref={inputRef}
                      type="text"
                      value={currentInput}
                      onChange={(e) => setCurrentInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      className="absolute inset-0 w-full bg-transparent text-transparent outline-none border-none"
                      style={{ caretColor: "transparent" }}
                      spellCheck={false}
                      autoComplete="off"
                      autoFocus
                    />
                    <span className="text-foreground">{currentInput}</span>
                    <span
                      className={`inline-block w-2 h-4 bg-emerald-400 ml-0.5 align-middle transition-opacity ${
                        cursorBlink ? "opacity-100" : "opacity-0"
                      }`}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Hint */}
          <div className={`mt-4 text-center transition-all duration-500 ${bootComplete ? "opacity-100" : "opacity-0"}`}>
            <div className="flex items-center justify-center gap-3">
              <div className="h-px w-8 bg-gradient-to-r from-transparent to-gray-700" />
              <span className="text-muted-foreground text-xs font-mono tracking-wider">PRESS ENTER TO EXECUTE</span>
              <div className="h-px w-8 bg-gradient-to-l from-transparent to-gray-700" />
            </div>
          </div>
        </div>
      </div>

      {/* Cyberpunk Animation Styles */}
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateX(-12px); }
          to { opacity: 1; transform: translateX(0); }
        }

        .cyber-grid {
          background-image:
            linear-gradient(rgba(255,107,44,0.15) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,107,44,0.15) 1px, transparent 1px);
          background-size: 50px 50px;
          animation: gridMove 20s linear infinite;
        }

        .dark .cyber-grid {
          background-image:
            linear-gradient(rgba(255,107,44,0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,107,44,0.1) 1px, transparent 1px);
        }

        @keyframes gridMove {
          0% { background-position: 0 0; }
          100% { background-position: 50px 50px; }
        }

        .scan-line {
          position: absolute;
          width: 100%;
          height: 2px;
          background: linear-gradient(90deg, transparent, rgba(255,107,44,0.5), rgba(0,255,255,0.3), transparent);
          box-shadow: 0 0 10px rgba(255,107,44,0.5), 0 0 20px rgba(0,255,255,0.3);
          animation: scanLine 4s linear infinite;
        }

        @keyframes scanLine {
          0% { top: -2px; opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }

        .crt-effect {
          background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.15),
            rgba(0, 0, 0, 0.15) 1px,
            transparent 1px,
            transparent 2px
          );
        }

        .glitch-overlay {
          animation: glitchOverlay 8s infinite;
        }

        @keyframes glitchOverlay {
          0%, 95%, 100% { opacity: 0; }
          96% { opacity: 0.1; background: rgba(255,0,0,0.1); transform: translateX(-2px); }
          97% { opacity: 0; }
          98% { opacity: 0.1; background: rgba(0,255,255,0.1); transform: translateX(2px); }
          99% { opacity: 0; }
        }

        .data-stream {
          width: 100%;
          height: 200%;
          background: linear-gradient(
            180deg,
            transparent 0%,
            rgba(0,255,255,0.3) 10%,
            rgba(255,107,44,0.5) 50%,
            rgba(0,255,255,0.3) 90%,
            transparent 100%
          );
          animation: dataStream 3s linear infinite;
        }

        @keyframes dataStream {
          0% { transform: translateY(-50%); }
          100% { transform: translateY(0%); }
        }

        .hex-float {
          position: absolute;
          animation: hexFloat 15s linear infinite;
        }

        @keyframes hexFloat {
          0% { top: 100%; opacity: 0; }
          10% { opacity: 0.3; }
          90% { opacity: 0.3; }
          100% { top: -10%; opacity: 0; }
        }

        .glow-line {
          animation: glowPulse 2s ease-in-out infinite;
        }

        @keyframes glowPulse {
          0%, 100% { opacity: 0.6; filter: drop-shadow(0 0 2px currentColor); }
          50% { opacity: 1; filter: drop-shadow(0 0 8px currentColor); }
        }

        .dark .cyber-text {
          text-shadow: 0 0 10px rgba(0,255,255,0.5);
        }

        .dark .terminal-cyber {
          background: linear-gradient(180deg, rgba(10,10,10,0.98) 0%, rgba(5,5,5,0.99) 100%);
        }

        .dark .text-glow-success {
          text-shadow: 0 0 10px rgba(52,211,153,0.8), 0 0 20px rgba(52,211,153,0.4);
        }
      `}</style>
    </div>
  );
}

export default SplashScreen;
