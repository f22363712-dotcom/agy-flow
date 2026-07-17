import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import './styles.css';

const cyan = '#00F2FE';
const blue = '#4FACFE';
const purple = '#B621FE';
const violet = '#1FD1F9';
const bg = '#0B0F19';
const ease = Easing.bezier(0.16, 1, 0.3, 1);

type SceneProps = {
  start: number;
  duration: number;
  children: (localFrame: number) => React.ReactNode;
};

const Scene: React.FC<SceneProps> = ({start, duration, children}) => {
  return (
    <Sequence from={start} durationInFrames={duration}>
      <SceneShell duration={duration}>{children}</SceneShell>
    </Sequence>
  );
};

const SceneShell: React.FC<{
  duration: number;
  children: (localFrame: number) => React.ReactNode;
}> = ({duration, children}) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(
    interpolate(frame, [0, 16], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease}),
    interpolate(frame, [duration - 16, duration], [1, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: ease,
    }),
  );
  return (
    <AbsoluteFill style={{opacity}}>
      {children(frame)}
    </AbsoluteFill>
  );
};

const Caption: React.FC<{kicker: string; title: string; sub?: string; compact?: boolean}> = ({
  kicker,
  title,
  sub,
  compact,
}) => (
  <div className={compact ? 'caption compact' : 'caption'}>
    <div className="kicker">{kicker}</div>
    <div className="captionTitle">{title}</div>
    {sub ? <div className="captionSub">{sub}</div> : null}
  </div>
);

const GlassPanel: React.FC<React.PropsWithChildren<{className?: string; style?: React.CSSProperties}>> = ({
  children,
  className,
  style,
}) => (
  <div className={`glass ${className ?? ''}`} style={style}>
    {children}
  </div>
);

const GridBackdrop: React.FC<{intensity?: number}> = ({intensity = 1}) => {
  const frame = useCurrentFrame();
  const shift = frame * 0.45;
  return (
    <AbsoluteFill className="backdrop" style={{backgroundColor: bg}}>
      <div className="auroraSweep" style={{transform: `translateY(${shift - 220}px) rotate(-18deg)`, opacity: 0.28 * intensity}} />
      <div className="auroraSweep secondary" style={{transform: `translateY(${620 - shift * 0.55}px) rotate(18deg)`, opacity: 0.22 * intensity}} />
      <div className="grid" style={{backgroundPosition: `0 ${shift}px`}} />
      <div className="vignette" />
    </AbsoluteFill>
  );
};

const Terminal: React.FC<{lines: string[]; active?: number; dense?: boolean}> = ({lines, active = lines.length, dense}) => {
  return (
    <GlassPanel className={dense ? 'terminal dense' : 'terminal'}>
      <div className="terminalTop">
        <span />
        <span />
        <span />
        <strong>powershell</strong>
      </div>
      <div className="terminalBody">
        {lines.slice(0, Math.max(0, active)).map((line, index) => (
          <div className={line.includes('PASSED') || line.includes('ack') ? 'line ok' : 'line'} key={`${line}-${index}`}>
            {line}
          </div>
        ))}
      </div>
    </GlassPanel>
  );
};

const LogoMark: React.FC<{scale?: number}> = ({scale = 1}) => (
  <div className="logoWrap" style={{transform: `scale(${scale})`}}>
    <div className="logoCore">agy</div>
    <div className="logoFlow">flow</div>
  </div>
);

const PainScene: React.FC<{frame: number}> = ({frame}) => {
  const warning = Math.sin(frame * 0.65) > -0.2 ? 1 : 0.35;
  const crack = interpolate(frame, [62, 90], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});
  const panels = [
    ['Cursor', 'Error: stale prompt', 'Paste #17 again'],
    ['Claude Code', 'context window 98%', 'summary drift'],
    ['Copilot', 'Context Lost!', 'retry suggestion'],
  ];
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={0.35} />
      <div className="triple">
        {panels.map((panel, index) => (
          <GlassPanel
            key={panel[0]}
            className="toolPane"
            style={{
              transform: `translateY(${interpolate(frame, [0, 30], [90 + index * 40, 0], {extrapolateRight: 'clamp', easing: ease})}px)`,
            }}
          >
            <div className="toolName">{panel[0]}</div>
            <div className="fakeCode">
              <span />
              <span />
              <span />
              <span />
            </div>
            <div className={panel[1].includes('Context') ? 'toolAlert hot' : 'toolAlert'}>{panel[1]}</div>
            <div className="toolHint">{panel[2]}</div>
          </GlassPanel>
        ))}
      </div>
      <div className="stressFace" style={{transform: `scale(${spring({frame, fps: 30, config: {damping: 9}})}) rotate(${Math.sin(frame / 4) * 4}deg)`}}>
        <span className="eye leftEye" />
        <span className="eye rightEye" />
        <span className="mouth" />
      </div>
      <div className="contextLost" style={{opacity: warning}}>Context Lost!</div>
      <div className="blackCrack" style={{clipPath: `inset(0 ${50 - crack * 50}% 0 ${50 - crack * 50}%)`}} />
      <Caption kicker="痛点" title="工具切来切去，上下文又丢了？" sub="复制、粘贴、重讲一遍，协作链路被打断。" />
    </AbsoluteFill>
  );
};

const SolutionScene: React.FC<{frame: number}> = ({frame}) => {
  const logoScale = spring({frame, fps: 30, config: {damping: 14, stiffness: 95}});
  const pulse = 1 + Math.sin(frame / 12) * 0.035;
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={1} />
      <div className="glassHalo" />
      <div className="centerStage">
        <LogoMark scale={logoScale * pulse} />
        <div className="slogan">一个任务，三倍智能</div>
        <div className="tagline">跨 AI 编码工具的多 Agent 协同框架</div>
      </div>
      <div className="miniBlackboard" style={{opacity: interpolate(frame, [78, 112], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
        <span>Shared Blackboard</span>
      </div>
    </AbsoluteFill>
  );
};

const StartScene: React.FC<{frame: number}> = ({frame}) => {
  const active = Math.floor(interpolate(frame, [12, 120], [1, 7], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={0.8} />
      <Caption kicker="起点接力" title="一个命令启动任务" sub="Antigravity 进入隔离 worktree，并加载设计规范。" compact />
      <div className="ideLabel">Antigravity</div>
      <div className="startLayout">
        <Terminal
          active={active}
          lines={[
            'PS D:\\multi_agent_collaboration> agent-relay start task-018',
            '[route] writer=antigravity reviewers=claude,codex',
            '[workspace] creating isolated git worktree',
            '[context] loading task-018-storyboard.md',
            '[spec] 1080x1920 | 30fps | 35s',
            '[handoff] blackboard ready',
            '[ok] visual design phase started',
          ]}
        />
        <GlassPanel className="worktreeCard">
          <div className="folderIcon">D:\\worktrees\\task-018</div>
          <div className="specRow"><b>palette</b><span>#00F2FE</span><span>#B621FE</span></div>
          <div className="specRow"><b>font</b><span>Outfit</span><span>OPPO Sans</span></div>
          <div className="specRow"><b>mode</b><span>handoff</span><span>writer</span></div>
          <div className="greenLines" />
        </GlassPanel>
      </div>
    </AbsoluteFill>
  );
};

const BlackboardScene: React.FC<{frame: number}> = ({frame}) => {
  const packet = interpolate(frame, [16, 120], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={0.9} />
      <Caption kicker="MCP 黑板传递" title="上下文自动接力" sub="任务状态、交接记录和代码进度写入共享黑板。" compact />
      <svg className="dataSvg" viewBox="0 0 1080 1920">
        <defs>
          <linearGradient id="flowGradient" x1="0" x2="1">
            <stop offset="0%" stopColor={cyan} />
            <stop offset="48%" stopColor={blue} />
            <stop offset="100%" stopColor={purple} />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="9" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path className="flowPath" d="M170 760 C360 610 470 1010 650 850 S840 720 935 940" />
        <circle cx={170 + packet * 765} cy={760 + Math.sin(packet * Math.PI * 3) * 110} r="20" fill="url(#flowGradient)" filter="url(#glow)" />
      </svg>
      <GlassPanel className="jsonCard leftJson">
        <div className="fileName">task-017.json</div>
        <code>{'{ "from_agent": "antigravity",'}</code>
        <code>{'  "to_agent": "claude",'}</code>
        <code>{'  "summary": "连接测试成功",'}</code>
        <code>{'  "acked_by": "claude" }'}</code>
      </GlassPanel>
      <GlassPanel className="pipeCard">
        <div>MCP Server</div>
        <span>handoffs/current</span>
        <strong>Shared Blackboard</strong>
      </GlassPanel>
      <GlassPanel className="jsonCard rightJson">
        <div className="fileName">task-018.json</div>
        <code>{'{ "writer": "Codex",'}</code>
        <code>{'  "mode": "handoff",'}</code>
        <code>{'  "role": "writer",'}</code>
        <code>{'  "task_id": "task-018" }'}</code>
      </GlassPanel>
    </AbsoluteFill>
  );
};

const ClaudeScene: React.FC<{frame: number}> = ({frame}) => {
  const active = Math.floor(interpolate(frame, [8, 165], [1, 9], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={0.75} />
      <Caption kicker="终点接棒" title="Claude Code 秒级读取上下文" sub="不用手动传文件，直接继续测试、实现和提审。" compact />
      <div className="ideLabel claude">Claude Code</div>
      <div className="claudeLayout">
        <Terminal
          active={active}
          lines={[
            '$ agent-relay status task-018',
            'handoff_id: 217dc777f48a3b7a4d2c15ae',
            'writer: Codex | reviewers: Codex, claude',
            'blackboard: current/task-018.json loaded',
            '$ pytest -q',
            'test_handoff.py ........ PASSED',
            'test_mcp_server.py ..... PASSED',
            'quality gate: PASSED',
            '$ agent-relay submit task-018',
          ]}
        />
        <div className="passedBadge" style={{transform: `scale(${1 + Math.sin(frame / 8) * 0.04})`}}>PASSED</div>
      </div>
    </AbsoluteFill>
  );
};

const DashboardScene: React.FC<{frame: number}> = ({frame}) => {
  const bars = [0.78, 0.54, 0.89, 0.66, 0.92];
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={1} />
      <Caption kicker="价值总结" title="跨 AI 工具的多 Agent 协同" sub="让不同 AI 专注各自擅长的事，任务状态自然流动。" compact />
      <div className="dashboard">
        <GlassPanel className="dashHero">
          <div className="dashTitle">agent-relay Dashboard</div>
          <div className="chain">
            {['Antigravity', 'Codex', 'Claude'].map((agent, index) => (
              <React.Fragment key={agent}>
                <div className="agentNode">
                  <span>{agent}</span>
                  <b>{index === 0 ? 'storyboard' : index === 1 ? 'video' : 'review'}</b>
                </div>
                {index < 2 ? <div className="chainLine" /> : null}
              </React.Fragment>
            ))}
          </div>
        </GlassPanel>
        <GlassPanel className="metricCard">
          <span>handoff latency</span>
          <strong>0.2s</strong>
          <small>MCP blackboard read</small>
        </GlassPanel>
        <GlassPanel className="metricCard purpleMetric">
          <span>context reuse</span>
          <strong>100%</strong>
          <small>no copy-paste loop</small>
        </GlassPanel>
        <GlassPanel className="chartCard">
          <div className="chartTitle">Token cost analysis</div>
          <div className="bars">
            {bars.map((bar, index) => (
              <span
                key={bar}
                style={{
                  height: `${bar * 210}px`,
                  transform: `scaleY(${interpolate(frame, [20 + index * 8, 70 + index * 8], [0.1, 1], {
                    extrapolateLeft: 'clamp',
                    extrapolateRight: 'clamp',
                    easing: ease,
                  })})`,
                }}
              />
            ))}
          </div>
        </GlassPanel>
      </div>
    </AbsoluteFill>
  );
};

const CtaScene: React.FC<{frame: number}> = ({frame}) => {
  const click = spring({frame: frame - 45, fps: 30, config: {damping: 8, stiffness: 120}});
  const ripple = interpolate(frame, [48, 88], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill>
      <GridBackdrop intensity={0.55} />
      <div className="cta">
        <div className="githubMark">GH</div>
        <div className="repo">github.com/f22363712-dotcom/agent-relay</div>
        <button className="starButton" style={{transform: `scale(${1 - click * 0.05})`}}>
          <span className="star">★</span>
          Star
        </button>
        <div className="ripple" style={{opacity: 1 - ripple, transform: `scale(${0.35 + ripple * 2.4})`}} />
        <div className="finalLine">即刻体验，让 AI 协作飞起来</div>
      </div>
    </AbsoluteFill>
  );
};

export const AgentRelayPromo: React.FC = () => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill className="videoRoot">
      <Audio src={staticFile('audio/ambient.wav')} volume={(frame) => interpolate(frame, [0, fps, 1020, 1050], [0, 0.22, 0.22, 0])} />
      <Scene start={0} duration={90}>{(frame) => <PainScene frame={frame} />}</Scene>
      <Scene start={90} duration={120}>{(frame) => <SolutionScene frame={frame} />}</Scene>
      <Scene start={210} duration={150}>{(frame) => <StartScene frame={frame} />}</Scene>
      <Scene start={360} duration={180}>{(frame) => <BlackboardScene frame={frame} />}</Scene>
      <Scene start={540} duration={210}>{(frame) => <ClaudeScene frame={frame} />}</Scene>
      <Scene start={750} duration={210}>{(frame) => <DashboardScene frame={frame} />}</Scene>
      <Scene start={960} duration={90}>{(frame) => <CtaScene frame={frame} />}</Scene>
    </AbsoluteFill>
  );
};
