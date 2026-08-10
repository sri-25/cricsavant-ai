import { useMemo, useState } from "react";
import {
  Activity, ArrowUpRight, BarChart3, Bot, ChevronDown, ChevronRight, Circle,
  CornerDownLeft, Database, Landmark, MessageSquare, NotebookPen, Play,
  Plus, Search, Send, Sparkles, Target, Terminal, TrendingUp, Trophy, Users, Wallet,
} from "lucide-react";
import {
  Bar, BarChart, Cell, Pie, PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";

/* ================= DESIGN TOKENS =================
   Slate/zinc dark, 2026 SaaS idiom: #0b0f17 canvas, #161b26 surfaces,
   #1e293b borders, glass blur, franchise accent glows. */
const cn = (...c) => c.filter(Boolean).join(" ");

/* ================= MOCK DATA ================= */
const FRANCHISES = [
  { id: "CSK", name: "Chennai Super Kings", color: "#eab308", purse: 2.4, purseTotal: 125, squad: 26, cap: 25, overseas: 9, osCap: 8, venue: "MA Chidambaram Stadium", bat: 11, bowl: 4, ar: 10, wk: 1 },
  { id: "MI", name: "Mumbai Indians", color: "#3b82f6", purse: 0.55, purseTotal: 125, squad: 25, cap: 25, overseas: 8, osCap: 8, venue: "Wankhede Stadium", bat: 9, bowl: 8, ar: 6, wk: 2 },
  { id: "RCB", name: "Royal Challengers Bengaluru", color: "#ef4444", purse: 0.25, purseTotal: 125, squad: 25, cap: 25, overseas: 8, osCap: 8, venue: "M Chinnaswamy Stadium", bat: 10, bowl: 8, ar: 5, wk: 2 },
  { id: "RR", name: "Rajasthan Royals", color: "#ec4899", purse: 2.65, purseTotal: 125, squad: 26, cap: 25, overseas: 8, osCap: 8, venue: "Sawai Mansingh Stadium", bat: 10, bowl: 7, ar: 7, wk: 2 },
  { id: "GT", name: "Gujarat Titans", color: "#6366f1", purse: 1.95, purseTotal: 125, squad: 25, cap: 25, overseas: 7, osCap: 8, venue: "Narendra Modi Stadium", bat: 9, bowl: 9, ar: 5, wk: 2 },
  { id: "SRH", name: "Sunrisers Hyderabad", color: "#f97316", purse: 5.45, purseTotal: 125, squad: 25, cap: 25, overseas: 8, osCap: 8, venue: "Rajiv Gandhi Intl. Stadium", bat: 10, bowl: 8, ar: 5, wk: 2 },
];

const PLAYERS = [
  {
    name: "JJ Bumrah", team: "MI", role: "Strike Bowler", country: "India", overseas: false,
    metrics: [{ k: "Recent Economy", v: "7.40", trend: -0.3, good: true }, { k: "Recent Wickets", v: "54", trend: 6, good: true }, { k: "Career Wickets", v: "308", trend: null }, { k: "SR Percentile", v: "0.93", trend: 0.02, good: true }],
    radar: [{ axis: "Powerplay", value: 88 }, { axis: "Middle", value: 74 }, { axis: "Death", value: 96 }, { axis: "Wickets", value: 91 }, { axis: "Control", value: 89 }],
    phases: [{ phase: "Powerplay", econ: 6.68 }, { phase: "Middle", econ: 6.46 }, { phase: "Death", econ: 7.91 }],
  },
  {
    name: "Devon Conway", team: "CSK", role: "Anchor Batter", country: "New Zealand", overseas: true,
    metrics: [{ k: "Recent SR", v: "135", trend: 4, good: true }, { k: "Recent Avg", v: "41.2", trend: 2.1, good: true }, { k: "Career Runs", v: "4,102", trend: null }, { k: "Home SR (Chepauk)", v: "131", trend: null }],
    radar: [{ axis: "Powerplay", value: 78 }, { axis: "Middle", value: 84 }, { axis: "Death", value: 61 }, { axis: "Chase", value: 82 }, { axis: "Finisher", value: 44 }],
    phases: [{ phase: "Powerplay", econ: 128 }, { phase: "Middle", econ: 136 }, { phase: "Death", econ: 158 }],
  },
  {
    name: "Sanju Samson", team: "RR", role: "WK Batter", country: "India", overseas: false,
    metrics: [{ k: "Recent SR", v: "159", trend: 11, good: true }, { k: "Recent Avg", v: "38.6", trend: 1.4, good: true }, { k: "Career Runs", v: "4,704", trend: null }, { k: "Home SR (Jaipur)", v: "151", trend: null }],
    radar: [{ axis: "Powerplay", value: 72 }, { axis: "Middle", value: 88 }, { axis: "Death", value: 84 }, { axis: "Chase", value: 79 }, { axis: "Finisher", value: 70 }],
    phases: [{ phase: "Powerplay", econ: 139 }, { phase: "Middle", econ: 152 }, { phase: "Death", econ: 171 }],
  },
];

const SCATTER = Array.from({ length: 60 }, (_, i) => ({
  x: Math.round(Math.random() * 100) / 100, y: Math.round(Math.random() * 100) / 100,
  type: i % 3 === 0 ? "strike" : i % 3 === 1 ? "containment" : "balanced",
}));

const NOTEBOOK = [
  { type: "Retention Plan", ts: "Aug 09 · 21:40", by: "agent", excerpt: "Retain: Conway (SR 135, home 131/10 inns), Gaikwad, Samson-watch... Release: 3 fringe all-rounders frees ₹4.1 cr..." },
  { type: "Auction Targets", ts: "Aug 09 · 21:52", by: "user", excerpt: "Priority 1: strike bowler ≤ ₹1.5 cr base. Candidates: 2 with sub-8 death economy in pool..." },
  { type: "Playing XI", ts: "Aug 09 · 22:04", by: "agent", excerpt: "Conway · Gaikwad · Dube · Samson(wk) · ... Impact: specialist death bowler for 2nd innings defence..." },
];

const CHAT_SEED = [
  { role: "user", text: "Should I retain my current squad or make changes?" },
  {
    role: "ai",
    text: "Based on squad retention analysis, CSK's top order is in strong form — **Conway (SR 135, home 131 across 10 inns)**, **Gaikwad (SR 130, home 137/25)**, and **Samson (SR 159)** are clear retains. Concerns sit in the bowling unit: two specialists show no qualifying recent sample. With **₹2.40 cr purse** and squad at **26/25**, at least one release is mandatory — I'd start with the thin-sample overseas all-rounders to also clear the 9/8 overseas breach.",
    tools: ["get_squad_retention_analysis({franchise:'CSK'})", "get_franchise_status({franchise:'CSK'})"],
  },
];

const PIPELINE_LOGS = [
  "21:44:02 INFO  cdc.sync  change_log → ops.lb_change_log_history",
  "21:44:03 INFO  cdc.sync  38/38 events materialized · lag 0",
  "21:44:03 INFO  vector    news_index refreshed · 369 docs",
  "21:44:04 INFO  agent     7 tools registered · gpt-oss-120b ready",
];

/* ================= PRIMITIVES ================= */
const Badge = ({ tone = "slate", children }) => {
  const tones = {
    slate: "bg-slate-500/10 text-slate-300 border-slate-500/20",
    rose: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    blue: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold", tones[tone])}>{children}</span>;
};

const Card = ({ className, glow, children }) => (
  <div
    className={cn("relative rounded-2xl border border-slate-800/60 bg-[#161b26]/90 backdrop-blur-md shadow-lg shadow-black/20", className)}
    style={glow ? { boxShadow: `0 0 0 1px ${glow}22, 0 8px 40px -12px ${glow}33` } : undefined}
  >
    {children}
  </div>
);

const Label = ({ children }) => (
  <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{children}</div>
);

const Progress = ({ value, color = "#3b82f6" }) => (
  <div className="mt-2 h-1.5 w-full rounded-full bg-slate-800">
    <div className="h-1.5 rounded-full transition-all duration-700" style={{ width: `${Math.min(value, 100)}%`, background: color }} />
  </div>
);

const TeamAvatar = ({ f, size = 36 }) => (
  <div
    className="flex items-center justify-center rounded-xl font-extrabold text-white shadow-inner"
    style={{ width: size, height: size, background: `linear-gradient(140deg, ${f.color}, ${f.color}88)`, fontSize: size * 0.34 }}
  >
    {f.id}
  </div>
);

const ChartTip = ({ active, payload, label }) =>
  active && payload?.length ? (
    <div className="rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs text-slate-200 shadow-xl">
      {label && <div className="mb-1 font-bold">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <Circle size={7} fill={p.color || p.payload?.fill} stroke="none" />
          {p.name}: <b>{p.value}</b>
        </div>
      ))}
    </div>
  ) : null;

/* ================= NAV RAIL ================= */
const NAV = [
  { id: "chat", icon: MessageSquare, label: "AI Analyst" },
  { id: "strategy", icon: Landmark, label: "Strategy Center" },
  { id: "players", icon: Search, label: "Players" },
  { id: "league", icon: BarChart3, label: "League Analytics" },
];

function Rail({ tab, setTab, franchise, setFranchise }) {
  const [open, setOpen] = useState(false);
  return (
    <aside className="flex h-full w-64 flex-col border-r border-slate-800/60 bg-slate-900/80 backdrop-blur-md">
      <div className="flex items-center gap-3 border-b border-slate-800/60 px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 shadow-lg shadow-amber-500/20">
          <Trophy size={20} className="text-slate-950" />
        </div>
        <div>
          <div className="font-extrabold tracking-tight text-slate-100">CricSavant AI</div>
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Franchise Strategy</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "group flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-all",
              tab === id ? "bg-slate-800/90 text-white shadow-inner" : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200",
            )}
          >
            <Icon size={17} className={tab === id ? "text-amber-400" : "text-slate-500 group-hover:text-slate-300"} />
            {label}
            {tab === id && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-amber-400" />}
          </button>
        ))}
      </nav>

      {/* Franchise selector */}
      <div className="relative border-t border-slate-800/60 p-3">
        <button
          onClick={() => setOpen(!open)}
          className="flex w-full items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2.5 transition-colors hover:border-slate-700"
        >
          <TeamAvatar f={franchise} />
          <div className="flex-1 text-left">
            <div className="text-sm font-bold text-slate-100">{franchise.id}</div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <Wallet size={11} /> ₹{franchise.purse} cr · <Users size={11} /> {franchise.squad}/{franchise.cap}
            </div>
          </div>
          <ChevronDown size={16} className={cn("text-slate-500 transition-transform", open && "rotate-180")} />
        </button>
        {open && (
          <div className="absolute bottom-full left-3 right-3 mb-2 overflow-hidden rounded-xl border border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur-xl">
            {FRANCHISES.map((f) => (
              <button
                key={f.id}
                onClick={() => { setFranchise(f); setOpen(false); }}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-slate-800/70"
              >
                <TeamAvatar f={f} size={28} />
                <span className="flex-1 truncate text-sm font-semibold text-slate-200">{f.name}</span>
                <span className="text-[11px] font-bold text-slate-400">₹{f.purse}cr</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

/* ================= TAB 1: AI ANALYST ================= */
const CHIPS = [
  { icon: Target, text: "Squad Weakness Triaging" },
  { icon: Activity, text: "Player Injury & Availability" },
  { icon: Landmark, text: "Venue Matchup Strategy" },
  { icon: NotebookPen, text: "Saved Strategy Notes" },
];

function ToolLog({ tools }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/60">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200">
        <ChevronRight size={13} className={cn("transition-transform", open && "rotate-90")} />
        <Terminal size={13} className="text-emerald-400" /> Tool Call Execution Logs · {tools.length}
      </button>
      {open && (
        <div className="border-t border-slate-800 px-4 py-2.5 font-mono text-[11px] leading-6 text-emerald-300/90">
          {tools.map((t, i) => <div key={i}>▸ {t}</div>)}
        </div>
      )}
    </div>
  );
}

function ChatTab({ franchise }) {
  const [messages, setMessages] = useState(CHAT_SEED);
  const [input, setInput] = useState("");
  const send = (text) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { role: "user", text }, {
      role: "ai", streaming: true,
      text: `Running that through ${franchise.name}'s real squad data, form splits, and the live auction pool...`,
      tools: ["get_franchise_status()", "get_squad_retention_analysis()"],
    }]);
    setInput("");
  };
  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-800/60 px-8 py-4">
        <div className="flex items-center gap-3">
          <TeamAvatar f={franchise} size={34} />
          <div>
            <div className="text-sm font-extrabold text-slate-100">AI Analyst — {franchise.name}</div>
            <div className="text-[11px] text-slate-500">Grounded strategy conversation</div>
          </div>
        </div>
        <Badge tone="emerald"><Circle size={7} className="animate-pulse fill-emerald-400" /> Real-time Stats · Live CDF Sync</Badge>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-8 py-6 pb-36">
        <div className="flex flex-wrap gap-2">
          {CHIPS.map(({ icon: Icon, text }) => (
            <button
              key={text}
              onClick={() => send(text)}
              className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/70 px-3.5 py-2 text-xs font-semibold text-slate-300 shadow-sm transition-all hover:-translate-y-0.5 hover:text-white"
              style={{ borderLeft: `3px solid ${franchise.color}` }}
            >
              <Icon size={14} style={{ color: franchise.color }} /> {text}
            </button>
          ))}
        </div>

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[70%] rounded-2xl rounded-br-md bg-slate-800 px-4 py-3 text-sm leading-relaxed text-slate-100 shadow-md">{m.text}</div>
            </div>
          ) : (
            <div key={i} className="flex gap-3">
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 shadow-lg shadow-amber-500/20">
                <Bot size={16} className="text-slate-950" />
              </div>
              <Card className="max-w-[78%] px-5 py-4" glow={franchise.color}>
                <div className="text-sm leading-relaxed text-slate-200" dangerouslySetInnerHTML={{ __html: m.text.replace(/\*\*(.+?)\*\*/g, "<b class='text-white'>$1</b>") }} />
                {m.streaming && (
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-amber-400" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-amber-400 [animation-delay:120ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-amber-400 [animation-delay:240ms]" />
                    streaming
                  </div>
                )}
                {m.tools && <ToolLog tools={m.tools} />}
              </Card>
            </div>
          ),
        )}
      </div>

      {/* Floating dock input */}
      <div className="absolute bottom-6 left-1/2 w-[min(760px,90%)] -translate-x-1/2">
        <div className="flex items-center gap-2 rounded-2xl border border-slate-700/80 bg-slate-900/85 px-4 py-3 shadow-2xl shadow-black/50 backdrop-blur-xl">
          <Sparkles size={17} className="shrink-0 text-amber-400" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)}
            placeholder={`Message CricSavant about ${franchise.id}...`}
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none"
          />
          <kbd className="hidden items-center gap-1 rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] font-bold text-slate-400 sm:flex">
            <CornerDownLeft size={10} /> Enter
          </kbd>
          <button
            onClick={() => send(input)}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-lg shadow-blue-500/30 transition-transform hover:scale-105"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ================= TAB 2: STRATEGY CENTER ================= */
const PLAYS = [
  { id: "retention", icon: NotebookPen, title: "Retention & Release", desc: "Retain / release / borderline with purse freed" },
  { id: "auction", icon: Target, title: "Auction Plan", desc: "Gap-targeted signings vs. purse math" },
  { id: "xi", icon: Trophy, title: "Best XI + Impact", desc: "Strongest XI, venue-fit, impact sub" },
];

function StrategyTab({ franchise }) {
  const [play, setPlay] = useState("retention");
  const donut = [
    { name: "Batters", value: franchise.bat, fill: "#f59e0b" },
    { name: "Bowlers", value: franchise.bowl, fill: "#3b82f6" },
    { name: "All-rounders", value: franchise.ar, fill: "#8b5cf6" },
    { name: "Keepers", value: franchise.wk, fill: "#14b8a6" },
  ];
  const overCap = franchise.squad > franchise.cap;
  const overOs = franchise.overseas > franchise.osCap;
  return (
    <div className="space-y-6 overflow-y-auto px-8 py-6">
      {/* Ticker */}
      <div className="overflow-hidden rounded-xl border border-slate-800/60 bg-slate-900/70 py-2.5 backdrop-blur-md">
        <div className="flex w-max animate-[csvticker_40s_linear_infinite] gap-10 pl-10">
          {[...FRANCHISES, ...FRANCHISES].map((f, i) => (
            <span key={i} className="flex items-center gap-2.5 text-xs font-semibold text-slate-400">
              <TeamAvatar f={f} size={22} /> <b className="text-slate-200">{f.id}</b> ₹{f.purse} cr · {f.squad}/{f.cap}
            </span>
          ))}
        </div>
        <style>{`@keyframes csvticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }`}</style>
      </div>

      {/* Executive banner */}
      <Card className="flex items-center gap-5 px-6 py-5" glow={franchise.color}>
        <TeamAvatar f={franchise} size={58} />
        <div className="flex-1">
          <div className="text-xl font-extrabold tracking-tight text-white">{franchise.name}</div>
          <div className="text-xs text-slate-400">{franchise.venue}</div>
        </div>
        {overCap && <Badge tone="rose">Squad over cap</Badge>}
        {overOs && <Badge tone="rose">Overseas over cap</Badge>}
        {!overCap && !overOs && <Badge tone="emerald">Auction ready</Badge>}
      </Card>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Card className="px-5 py-4">
          <Label>Purse Remaining</Label>
          <div className="mt-1 text-2xl font-extrabold text-emerald-400">₹{franchise.purse} cr</div>
          <Progress value={(franchise.purse / franchise.purseTotal) * 100} color="#10b981" />
        </Card>
        <Card className="px-5 py-4">
          <div className="flex items-center justify-between"><Label>Squad Capacity</Label>{overCap && <Badge tone="rose">+{franchise.squad - franchise.cap}</Badge>}</div>
          <div className="mt-1 text-2xl font-extrabold text-white">{franchise.squad} / {franchise.cap}</div>
          <Progress value={(franchise.squad / franchise.cap) * 100} color={overCap ? "#f43f5e" : "#3b82f6"} />
        </Card>
        <Card className="px-5 py-4">
          <div className="flex items-center justify-between"><Label>Overseas Limit</Label>{overOs && <Badge tone="rose">+{franchise.overseas - franchise.osCap}</Badge>}</div>
          <div className="mt-1 text-2xl font-extrabold text-white">{franchise.overseas} / {franchise.osCap}</div>
          <Progress value={(franchise.overseas / franchise.osCap) * 100} color={overOs ? "#f43f5e" : "#8b5cf6"} />
        </Card>
        <Card className="px-5 py-4">
          <Label>Balance</Label>
          <div className="mt-1 text-2xl font-extrabold text-white">{franchise.bat}·{franchise.bowl}·{franchise.ar}·{franchise.wk}</div>
          <div className="mt-1 text-[11px] text-slate-500">Bat · Bowl · AR · WK</div>
        </Card>
      </div>

      {/* Plays */}
      <div>
        <Label>Strategy Plays</Label>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {PLAYS.map(({ id, icon: Icon, title, desc }) => (
            <button
              key={id}
              onClick={() => setPlay(id)}
              className={cn(
                "rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5",
                play === id ? "border-blue-500/60 bg-blue-500/10 shadow-lg shadow-blue-500/10" : "border-slate-800 bg-slate-900/60 hover:border-slate-700",
              )}
            >
              <Icon size={18} className={play === id ? "text-blue-400" : "text-slate-500"} />
              <div className="mt-2 text-sm font-bold text-slate-100">{title}</div>
              <div className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{desc}</div>
            </button>
          ))}
        </div>
        <button className="mt-4 flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-blue-700 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-500/30 transition-transform hover:scale-[1.02]">
          <Play size={15} /> Run Strategy Engine
        </button>
      </div>

      {/* Split view */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="col-span-2 px-5 py-4">
          <Label>Squad Composition</Label>
          <div className="relative">
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={donut} dataKey="value" innerRadius={62} outerRadius={88} paddingAngle={3} stroke="none">
                  {donut.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Pie>
                <Tooltip content={<ChartTip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-2xl font-extrabold text-white">{franchise.squad}</div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">players</div>
            </div>
          </div>
          <div className="mt-1 flex flex-wrap justify-center gap-3 text-[11px] text-slate-400">
            {donut.map((d) => <span key={d.name} className="flex items-center gap-1.5"><Circle size={7} fill={d.fill} stroke="none" />{d.name} {d.value}</span>)}
          </div>
        </Card>
        <Card className="col-span-3 overflow-hidden">
          <div className="px-5 pt-4"><Label>Squad Data Grid</Label></div>
          <div className="mt-2 max-h-[290px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#161b26] text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <tr>{["Player", "Role", "Status"].map((h) => <th key={h} className="px-5 py-2">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {[["MS Dhoni", "WK Batter", false], ["Devon Conway", "Anchor Batter", true], ["Ruturaj Gaikwad", "Top Order", false], ["Shivam Dube", "All-rounder", false], ["Matt Henry", "Strike Bowler", true], ["Akeal Hosein", "Spinner", true], ["Rahul Chahar", "Leg Spinner", false], ["Nathan Ellis", "Death Bowler", true]].map(([p, r, os]) => (
                  <tr key={p} className="text-slate-300 transition-colors hover:bg-slate-800/30">
                    <td className="px-5 py-2.5 font-semibold text-slate-100">{p}</td>
                    <td className="px-5 py-2.5"><Badge tone="blue">{r}</Badge></td>
                    <td className="px-5 py-2.5"><Badge tone={os ? "amber" : "slate"}>{os ? "✈️ Overseas" : "🏠 Domestic"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Notebook */}
      <div>
        <Label>Saved Strategy Notebook</Label>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {NOTEBOOK.map((n) => (
            <Card key={n.type} className="p-4 transition-transform hover:-translate-y-0.5">
              <div className="flex items-center justify-between">
                <Badge tone="amber">{n.type}</Badge>
                <span className="text-[10px] text-slate-500">{n.ts}</span>
              </div>
              <p className="mt-2.5 line-clamp-3 text-xs leading-relaxed text-slate-400">{n.excerpt}</p>
              <div className="mt-3 flex gap-2 text-[11px] font-bold text-blue-400">
                <button className="hover:text-blue-300">Export PDF</button>·<button className="hover:text-blue-300">JSON</button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ================= TAB 3: PLAYERS ================= */
function PlayersTab({ franchise }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(PLAYERS[0]);
  const results = useMemo(() => PLAYERS.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())), [q]);
  return (
    <div className="space-y-5 overflow-y-auto px-8 py-6 pb-28">
      {/* Command palette search */}
      <div className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-3 shadow-lg backdrop-blur-md">
        <Search size={17} className="text-slate-500" />
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search 2,465 players — fuzzy match handles 'Bumrah' → 'JJ Bumrah'..."
          className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none"
        />
        {["Role", "Overseas", "Team"].map((f) => (
          <button key={f} className="hidden items-center gap-1 rounded-lg border border-slate-800 px-2.5 py-1.5 text-[11px] font-bold text-slate-400 hover:border-slate-600 md:flex">
            {f} <ChevronDown size={12} />
          </button>
        ))}
        <kbd className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] font-bold text-slate-400">⌘K</kbd>
      </div>

      <div className="flex flex-wrap gap-2">
        {results.map((p) => (
          <button
            key={p.name} onClick={() => setSel(p)}
            className={cn("rounded-xl border px-3.5 py-2 text-xs font-bold transition-all",
              sel.name === p.name ? "border-amber-500/60 bg-amber-500/10 text-amber-300" : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-600")}
          >
            {p.name}
          </button>
        ))}
      </div>

      {/* Banner */}
      <Card className="flex flex-wrap items-center gap-5 px-6 py-5" glow="#f59e0b">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-slate-700 to-slate-800 text-xl font-extrabold text-slate-300 shadow-inner">
          {sel.name.split(" ").map((w) => w[0]).join("")}
        </div>
        <div className="flex-1">
          <div className="text-xl font-extrabold text-white">{sel.name}</div>
          <div className="mt-1 flex gap-2">
            <Badge tone="blue">{sel.role}</Badge>
            <Badge tone="slate">{sel.country}</Badge>
            <Badge tone={sel.overseas ? "amber" : "emerald"}>{sel.overseas ? "Overseas" : "Domestic"}</Badge>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {sel.metrics.map((m) => (
            <div key={m.k} className="rounded-xl border border-slate-800/80 bg-slate-900/60 px-4 py-2.5 backdrop-blur-sm">
              <Label>{m.k}</Label>
              <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="text-lg font-extrabold text-white">{m.v}</span>
                {m.trend != null && (
                  <span className={cn("flex items-center text-[11px] font-bold", m.good ? "text-emerald-400" : "text-rose-400")}>
                    <TrendingUp size={11} className={m.trend < 0 ? "rotate-180" : ""} /> {Math.abs(m.trend)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Charts grid */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="px-4 py-4">
          <Label>Performance Shape</Label>
          <ResponsiveContainer width="100%" height={240}>
            <RadarChart data={sel.radar} outerRadius={85}>
              <PolarGrid stroke="#1e293b" />
              <PolarAngleAxis dataKey="axis" tick={{ fill: "#64748b", fontSize: 11 }} />
              <PolarRadiusAxis tick={false} axisLine={false} />
              <Radar dataKey="value" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.25} strokeWidth={2} />
              <Tooltip content={<ChartTip />} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>
        <Card className="px-4 py-4">
          <Label>Phase Analysis</Label>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={sel.phases}>
              <defs>
                <linearGradient id="phaseGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" /><stop offset="100%" stopColor="#1e40af" />
                </linearGradient>
              </defs>
              <XAxis dataKey="phase" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip />} cursor={{ fill: "#1e293b55" }} />
              <Bar dataKey="econ" name="Rate" fill="url(#phaseGrad)" radius={[4, 4, 0, 0]} maxBarSize={46} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card className="px-4 py-4">
          <Label>Strike vs Containment Matrix</Label>
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart>
              <XAxis dataKey="x" name="Economy pct" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 1]} />
              <YAxis dataKey="y" name="Strike-rate pct" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 1]} />
              <ZAxis range={[28, 28]} />
              <Tooltip content={<ChartTip />} />
              <Scatter data={SCATTER.filter((s) => s.type === "strike")} fill="#f59e0b" opacity={0.75} />
              <Scatter data={SCATTER.filter((s) => s.type === "containment")} fill="#3b82f6" opacity={0.75} />
              <Scatter data={SCATTER.filter((s) => s.type === "balanced")} fill="#475569" opacity={0.6} />
              <Scatter data={[{ x: 0.93, y: 0.88 }]} fill="#fbbf24" shape="star" />
            </ScatterChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Action dock */}
      <div className="fixed bottom-6 left-1/2 z-10 flex -translate-x-1/2 gap-2 rounded-2xl border border-slate-700/80 bg-slate-900/90 px-3 py-2.5 shadow-2xl shadow-black/50 backdrop-blur-xl">
        {[{ icon: MessageSquare, t: "Ask AI Analyst" }, { icon: Plus, t: "Add to Target List" }, { icon: BarChart3, t: "Compare" }].map(({ icon: Icon, t }) => (
          <button key={t} className="flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-bold text-slate-300 transition-colors hover:bg-slate-800 hover:text-white">
            <Icon size={14} className="text-amber-400" /> {t}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ================= TAB 4: LEAGUE ANALYTICS ================= */
function LeagueTab() {
  const spend = FRANCHISES.map((f) => ({ name: f.id, Spent: +(f.purseTotal - f.purse).toFixed(1), Remaining: f.purse, color: f.color }));
  const totalLeft = FRANCHISES.reduce((s, f) => s + f.purse, 0);
  const richest = FRANCHISES.reduce((a, b) => (a.purse > b.purse ? a : b));
  const overCap = FRANCHISES.filter((f) => f.squad > f.cap || f.overseas > f.osCap);
  const [logsOpen, setLogsOpen] = useState(false);
  return (
    <div className="space-y-5 overflow-y-auto px-8 py-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="px-5 py-4"><Label>Total Purse in Play</Label><div className="mt-1 text-2xl font-extrabold text-amber-400">₹{totalLeft.toFixed(2)} cr</div><div className="mt-1 text-[11px] text-slate-500">combined remaining · all franchises</div></Card>
        <Card className="px-5 py-4"><Label>Max Purse Power</Label><div className="mt-1 flex items-center gap-2 text-2xl font-extrabold text-white"><TeamAvatar f={richest} size={26} />{richest.id}</div><div className="mt-1 text-[11px] text-slate-500">₹{richest.purse} cr remaining</div></Card>
        <Card className="px-5 py-4"><div className="flex items-center justify-between"><Label>Over-Cap Warnings</Label><Badge tone={overCap.length ? "rose" : "emerald"}>{overCap.length ? "action needed" : "clear"}</Badge></div><div className="mt-1 text-2xl font-extrabold text-rose-400">{overCap.length}</div><div className="mt-1 text-[11px] text-slate-500">franchises must release pre-auction</div></Card>
      </div>

      <Card className="px-5 py-4">
        <Label>Franchise Spend vs Remaining (₹ cr)</Label>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={spend} layout="vertical" margin={{ left: 10 }}>
            <XAxis type="number" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" tick={{ fill: "#94a3b8", fontSize: 12, fontWeight: 700 }} axisLine={false} tickLine={false} width={46} />
            <Tooltip content={<ChartTip />} cursor={{ fill: "#1e293b55" }} />
            <Bar dataKey="Spent" stackId="a" radius={[4, 0, 0, 4]} maxBarSize={18}>
              {spend.map((s, i) => <Cell key={i} fill={s.color} opacity={0.85} />)}
            </Bar>
            <Bar dataKey="Remaining" stackId="a" fill="#334155" radius={[0, 4, 4, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Card className="overflow-hidden">
        <div className="px-5 pt-4"><Label>Squad Balance Matrix</Label></div>
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <tr>{["Franchise", "Purse", "Squad", "Overseas", "Bat", "Bowl", "AR", "WK", "Home Venue"].map((h) => <th key={h} className="px-5 py-2">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {FRANCHISES.map((f) => (
              <tr key={f.id} className="text-slate-300 transition-colors hover:bg-slate-800/30">
                <td className="flex items-center gap-2.5 px-5 py-2.5 font-bold text-slate-100"><TeamAvatar f={f} size={24} />{f.id}</td>
                <td className="px-5 py-2.5 font-semibold text-emerald-400">₹{f.purse}</td>
                <td className="px-5 py-2.5">{f.squad > f.cap ? <Badge tone="rose">{f.squad}/{f.cap}</Badge> : `${f.squad}/${f.cap}`}</td>
                <td className="px-5 py-2.5">{f.overseas > f.osCap ? <Badge tone="rose">{f.overseas}/{f.osCap}</Badge> : `${f.overseas}/${f.osCap}`}</td>
                <td className="px-5 py-2.5">{f.bat}</td><td className="px-5 py-2.5">{f.bowl}</td>
                <td className="px-5 py-2.5">{f.ar}</td><td className="px-5 py-2.5">{f.wk}</td>
                <td className="px-5 py-2.5 text-xs text-slate-500">{f.venue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* MLOps terminal widget */}
      <Card className="overflow-hidden">
        <button onClick={() => setLogsOpen(!logsOpen)} className="flex w-full items-center gap-3 px-5 py-4">
          <Database size={16} className="text-emerald-400" />
          <span className="text-sm font-bold text-slate-100">Lakebase → Delta CDF Pipeline</span>
          <Badge tone="emerald"><Circle size={7} className="animate-pulse fill-emerald-400" /> Sync Active · 38 / 38 Delta Batches</Badge>
          <ChevronDown size={15} className={cn("ml-auto text-slate-500 transition-transform", logsOpen && "rotate-180")} />
        </button>
        {logsOpen && (
          <div className="border-t border-slate-800 bg-slate-950/80 px-5 py-3 font-mono text-[11px] leading-6 text-emerald-300/80">
            {PIPELINE_LOGS.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ================= ROOT ================= */
export default function CricSavantDashboard() {
  const [tab, setTab] = useState("chat");
  const [franchise, setFranchise] = useState(FRANCHISES[0]);
  return (
    <div className="flex h-screen bg-[#0b0f17] font-sans antialiased" style={{ fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* Ambient franchise glow */}
      <div className="pointer-events-none fixed inset-0" style={{ background: `radial-gradient(900px 500px at 85% -10%, ${franchise.color}14, transparent 60%)` }} />
      <Rail tab={tab} setTab={setTab} franchise={franchise} setFranchise={setFranchise} />
      <main className="relative flex-1 overflow-hidden">
        {tab === "chat" && <ChatTab franchise={franchise} />}
        {tab === "strategy" && <StrategyTab franchise={franchise} />}
        {tab === "players" && <PlayersTab franchise={franchise} />}
        {tab === "league" && <LeagueTab />}
      </main>
    </div>
  );
}
