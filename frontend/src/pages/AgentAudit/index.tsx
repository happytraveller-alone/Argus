import { Zap, Bot, Layers, ArrowRight, GitBranch } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useEffect, useRef } from "react";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";

type HomeScanCard = {
	key: "static" | "agent" | "hybrid";
	title: string;
	intro: string;
	icon: typeof Zap;
	targetRoute: string;
};

const homeScanCards: HomeScanCard[] = [
	{
		key: "static",
		title: "静态扫描",
		intro: "规则驱动漏洞检测",
		icon: Zap,
		targetRoute: "/tasks/static?openCreate=1&source=home-card",
	},
	{
		key: "agent",
		title: "智能扫描",
		intro: "AI Agent 代码推理",
		icon: Bot,
		targetRoute: "/tasks/intelligent?openCreate=1&source=home-card",
	},
	{
		key: "hybrid",
		title: "混合扫描",
		intro: "静态分析 + AI 推理",
		icon: Layers,
		targetRoute: "/tasks/hybrid?openCreate=1&source=home-card",
	},
];

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;

    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));

    document.head.appendChild(script);
  });
}

export function HomeScanCards() {
	const navigate = useNavigate();
	const { logoSrc, cycleLogoVariant } = useLogoVariant();

  const vantaRef = useRef<HTMLDivElement>(null);
  const vantaEffect = useRef<{ destroy: () => void } | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function initVanta() {
      try {
        await loadScript("https://cdnjs.cloudflare.com/ajax/libs/three.js/r134/three.min.js");
        await loadScript("https://cdn.jsdelivr.net/npm/vanta@latest/dist/vanta.net.min.js");

        if (cancelled || !vantaRef.current || !window.VANTA) return;

        vantaEffect.current = window.VANTA.NET({
          el: vantaRef.current,
          THREE: window.THREE,
          mouseControls: true,
          touchControls: true,
          gyroControls: false,
          color: 0x3b82f6,
          backgroundColor: 0x070b16,
          points: 14,
          maxDistance: 22,
          spacing: 18,
        });
      } catch (err) {
        console.warn("Vanta load failed:", err);
      }
    }

    initVanta();

    return () => {
      cancelled = true;
      vantaEffect.current?.destroy();
      vantaEffect.current = null;
    };
  }, []);

  return (
    <div
      ref={vantaRef}
      className="min-h-[100dvh] flex items-center justify-center relative overflow-hidden"
    >

      {/* ───────────────── iframe 背景 ───────────────── */}

      <div className="absolute inset-0 flex items-center justify-center z-10">

        <iframe
          src="http://localhost:5174"
          title="GitNexus"
          className="
            w-[1200px]
            h-[720px]
            border-0
            opacity-70
            rounded-xl
            scale-105
            shadow-[0_0_120px_rgba(0,0,0,0.9)]
            pointer-events-auto
          "
        />

      </div>

      {/* UI 层（默认鼠标穿透） */}

      <div className="relative z-20 w-full max-w-[1200px] mx-auto px-6 text-center pointer-events-none -mt-80">

        {/* Logo + 标题 */}

        <div className="mb-12 flex items-center justify-center gap-5">

          <button
            onClick={cycleLogoVariant}
            className="
              pointer-events-auto
              w-20 h-20 rounded-3xl
              border border-primary/40 bg-primary/10
              flex items-center justify-center
              shadow-[0_0_50px_rgba(59,130,246,0.5)]
              transition hover:scale-105
            "
          >
            <img
              src={logoSrc}
              alt="VulHunter"
              className="w-16 h-16 object-contain"
            />
          </button>

          <h1 className="text-6xl font-bold tracking-wider font-mono">
            VulHunter
          </h1>

        </div>

        {/* 主按钮 */}

        <div className="mb-14">

          <button
            onClick={() =>
              navigate("/tasks/hybrid?openCreate=1&source=home-primary")
            }
            className="
              pointer-events-auto
              group relative px-14 py-5 text-xl font-bold text-white rounded-2xl
              bg-gradient-to-r from-blue-500 to-indigo-600
              shadow-[0_0_35px_rgba(59,130,246,0.7)]
              transition hover:scale-105 hover:shadow-[0_0_60px_rgba(59,130,246,0.9)]
            "
          >
              <span className="flex items-center gap-3 justify-center">
                一键开始安全审计
                <ArrowRight className="w-6 h-6 transition group-hover:translate-x-1" />
              </span>

          </button>

        </div>

        {/* 信任信息 */}

        <div className="flex items-center justify-center gap-3 mb-14 flex-wrap">

          <span className="text-sm text-foreground/60">
            1000+ 漏洞规则 · AI Agent 推理
          </span>

          <span className="text-foreground/20 text-sm">|</span>
        </div>

        {/* 扫描模式卡片 */}

        <div className="mt-40 grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">

          {homeScanCards.map((card) => {

            const Icon = card.icon;

            return (

              <button
                key={card.key}
                onClick={() => navigate(card.targetRoute)}
                className="
                  pointer-events-auto
                  group relative backdrop-blur-sm
                  border border-white/10 bg-white/5
                  rounded-xl p-6 text-left transition
                  hover:border-primary/50 hover:bg-white/10 hover:-translate-y-1
                "
              >

                <ArrowRight className="absolute right-4 top-4 w-4 h-4 opacity-0 transition group-hover:opacity-100 group-hover:translate-x-1 text-primary" />

                <div className="flex items-center gap-3 mb-2">

                  <div className="p-2 rounded-md bg-primary/10 text-primary">
                    <Icon className="w-5 h-5" />
                  </div>

                  <h3 className="font-semibold text-lg">{card.title}</h3>

                </div>

                <p className="text-sm text-foreground/70">
                  {card.intro}
                </p>

              </button>

            );

          })}

        </div>

      </div>

    </div>
  );
}

export default HomeScanCards;