import { ArrowRight, Bot, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";

type HomeScanCard = {
  key: "static" | "agent";
  title: string;
  intro: string;
  detail: string;
  icon: typeof ShieldCheck;
  targetRoute: string;
};

const homeScanCards: HomeScanCard[] = [
  {
    key: "static",
    title: "静态审计",
    intro: "规则驱动漏洞检测",
    detail: "适合快速扫描代码仓库，按规则定位高风险缺陷与配置问题。",
    icon: ShieldCheck,
    targetRoute: "/tasks/static?openCreate=1&source=home-static",
  },
  {
    key: "agent",
    title: "智能审计",
    intro: "AI Agent 代码推理",
    detail: "适合复杂业务链路分析，让审计智能体追踪上下文并输出可复核证据。",
    icon: Bot,
    targetRoute: "/tasks/intelligent?openCreate=1&source=home-agent",
  },
];

export function HomeScanCards() {
  const navigate = useNavigate();
  const { logoSrc } = useLogoVariant();

  return (
    <div className="relative min-h-[calc(100dvh-4rem)] overflow-hidden bg-[linear-gradient(135deg,rgba(2,6,23,0.98),rgba(8,18,36,0.96)_48%,rgba(0,0,0,0.98))]">
      <div className="relative z-10 mx-auto grid min-h-[calc(100dvh-4rem)] w-full max-w-[1180px] grid-cols-1 items-center gap-10 px-6 py-14 md:grid-cols-2 lg:px-10">
        <div className="flex items-center justify-center">
          <img
            src={logoSrc}
            alt="Argus"
            className="w-full max-w-[26rem] object-contain sm:max-w-[30rem] lg:max-w-none"
          />
        </div>

        <div className="grid gap-5">
          {homeScanCards.map((card) => {
            const Icon = card.icon;

            return (
              <button
                key={card.key}
                onClick={() => navigate(card.targetRoute)}
                className="
                  pointer-events-auto
                  group relative overflow-hidden rounded-md border border-white/15
                  bg-white/[0.07] p-6 text-left shadow-[0_18px_54px_rgba(0,0,0,0.34)]
                  backdrop-blur-xl transition duration-300
                  hover:-translate-y-1 hover:border-primary/55 hover:bg-white/[0.11]
                  hover:shadow-[0_22px_70px_rgba(14,165,233,0.18)]
                  focus-visible:border-white/35 focus-visible:bg-white/[0.12]
                  focus-visible:outline focus-visible:outline-1 focus-visible:outline-white/55 focus-visible:outline-offset-2
                "
              >
                <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-80" />
                <span className="pointer-events-none absolute -right-16 -top-16 h-36 w-36 rounded-full bg-primary/10 blur-3xl transition group-hover:bg-primary/20" />

                <div className="relative flex items-start justify-between gap-5">
                  <div className="flex min-w-0 gap-4">
                    <span className="mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/15 text-primary">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-2xl font-semibold leading-tight text-foreground">
                        {card.title}
                      </span>
                      <span className="mt-1 block font-mono text-sm text-primary">
                        {card.intro}
                      </span>
                    </span>
                  </div>
                  <ArrowRight className="mt-2 h-6 w-6 shrink-0 text-primary transition duration-300 group-hover:translate-x-1" />
                </div>

                <p className="relative mt-5 max-w-xl text-base leading-7 text-foreground/70">
                  {card.detail}
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
