import React from 'react';
import {Composition} from 'remotion';
import {AgentRelayPromo} from './video/AgentRelayPromo';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="AgentRelayPromo"
      component={AgentRelayPromo}
      durationInFrames={1050}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
