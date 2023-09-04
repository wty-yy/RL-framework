from typing import NamedTuple
from katarl.envs import Env
from katarl.envs.atari_wrappers import (
    FireResetWrapper, 
    EpisodeLifeWrapper,
)

import gymnasium as gym
import numpy as np

INF = int(1e18)

atari_envs = [
    "Breakout-v4",
    "ALE/Breakout-v5"
]

# If joining a Env, the following parameters must be given.
# max_step = {
#     "CartPole-v1": 500,
#     "Breakout-v4": INF,
#     "ALE/Breakout-v5": INF,
# }
state_shape = {
    "CartPole-v1": (4,),
    # DELIT: Atari env has GrayColor and 4 frames stack
    "Breakout-v4": (210, 160, 3),
    "ALE/Breakout-v5": (210, 160, 3),
}
action_shape = {
    "CartPole-v1": (1,),
    "Breakout-v4": (1,),
    "ALE/Breakout-v5": (1,),
}
action_ndim = {
    "CartPole-v1": 2,
    "Breakout-v4": 4,
    "ALE/Breakout-v5": 4,
}
rewards = {
    "positive": {
        "CartPole-v1": 1,
        "Breakout-v4": None,
        "ALE/Breakout-v5": None,
    },
    "negative": {
        "CartPole-v1": 1,
        "Breakout-v4": None,
        "ALE/Breakout-v5": None,
    }
}

class GymEnv(Env):
    """
    The OpenAI Gymnasium, create a new Env by the Env.name
    """

    def __init__(self, args: NamedTuple = None):

        self.name, self.args = args.env_name, args
        if vars(args).get('num_envs') is None: args.num_envs = 1
        # if max_step.get(name) is None:
        #     raise Exception(f"Don't know the max_step of the environment: '{name}'")
        # if state_shape.get(name) is None:
        #     raise Exception(f"Don't know the state_shape of the environment: '{name}'")
        # if action_shape.get(name) is None:
        #     raise Exception(f"Don't know the action_shape of the environment: '{name}'")
        # if action_ndim.get(name) is None:
        #     raise Exception(f"Don't know the action_size of the environment: '{name}'")
        # if rewards['positive'].get(name) is None:
        #     raise Exception(f"Don't know the positive reward of the environment: '{name}'")
        # if rewards['negative'].get(name) is None:
        #     raise Exception(f"Don't know the negative reward of the environment: '{name}'")

        self.use_atari_wrapper = self.name in atari_envs
        self.envs = gym.vector.SyncVectorEnv([  # FIX: AsyncVectorEnv is slower than SyncVectorEnv
            self.make_env(i) for i in range(args.num_envs)
        ])
        if vars(args).get('neg_rewards'):
            self.neg_rewards = args.neg_rewards
        else: self.neg_rewards = rewards['negative'].get(self.name)
        super().__init__(
            args,
            state_shape=self.envs.single_observation_space.shape,
            action_shape=(1,),
            action_ndim=self.envs.single_action_space.n,
        )
    
    def make_env(self, idx):
        def thunk():
            is_pow2 = lambda x: x == int(2**int(np.log2(x)))
            if self.args.capture_video and idx == 0:
                env = gym.make(self.name, render_mode='rgb_array')  # FIX: render_mods is slower
                env = gym.wrappers.RecordVideo(
                    env, "logs/videos",
                    episode_trigger=lambda episode: True if is_pow2(episode+1) or episode % 128 == 0 else False,  # capture 1,2,4,8,...,512,N*1024
                    name_prefix=f"{idx}"
                )
            else:
                env = gym.make(self.name)
            env.action_space.seed(self.args.seed)
            env.observation_space.seed(self.args.seed)
            if self.use_atari_wrapper:
                env = EpisodeLifeWrapper(env)
                env = FireResetWrapper(env)
                env = gym.wrappers.ResizeObservation(env, (84, 84))
                env = gym.wrappers.GrayScaleObservation(env)
                env = gym.wrappers.FrameStack(env, 4)
            return env
        return thunk
    
    def step(self, action):
        self.reset_history()
        state, reward, terminal, truncated, _ = self.envs.step(action)
        terminal = terminal | truncated
        if rewards['positive'].get(self.name) is not None:
            reward = np.full_like(reward, rewards['positive'][self.name], dtype='float32')
        if self.neg_rewards is not None:
            reward[terminal ^ truncated] = self.neg_rewards
        self.add_history(['step_count', 'sum_reward'], [1, reward])
        state = self.check_state_shape(state)
        self.last_terminal = terminal
        return state, reward, terminal
    
    def reset(self):
        super().reset()  # reset step_count
        state, _ = self.envs.reset(
            seed=[self.args.seed+i for i in range(self.num_envs)]
        )
        state = self.check_state_shape(state)
        return state
    
    def check_state_shape(self, state):
        if self.use_atari_wrapper:
            # (8, 4, 210, 160) -> (8, 210, 160, 4)
            state = state.reshape(self.num_envs, *self.state_shape)
        return state

    def render(self):
        return self.envs.render()
    
    def close(self):
        self.envs.close()
