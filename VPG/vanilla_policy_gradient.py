# -*- coding: utf-8 -*-
"""Vanilla_policy_Gradient.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/17A8Wiu54ljtMV_QelYl6-CkUUSaYoLmw
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install git+https://github.com/eleurent/highway-env

import gym
import numpy as np
import highway_env
env = gym.make("highway-v0")

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.distributions import Categorical
import moviepy.editor as mpy
import matplotlib.pyplot as plt

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
eps = np.finfo(np.float32).eps.item()

screen_width, screen_height = 160, 160
config = {
            "offscreen_rendering": True,
            "observation": {
            "type": "GrayscaleObservation",
            "weights": [0.2989, 0.5870, 0.1140],  # weights for RGB conversion
            "stack_size": 4,
            "observation_shape": (screen_width, screen_height)
            },
          "collision_reward":-1,
            "screen_width": screen_width,
          "screen_height": screen_height,
          "scaling": 5.5,
          "policy_frequency": 2,
          "action": {
              "type": "DiscreteMetaAction"
          },
        'duration': 3000,
        'offroad_terminal':True,
        'policy_frequency':10,
        'simulation_frequency':10,
        'vehicles_count':20,
        }
env = gym.make('highway-v0')
env.configure(config)
observation = env.reset()
print(observation.shape)
print(env.action_space.sample())
print(env.config)

observation = env.reset()

def prepro(image):
    """ prepro 210x160x3 uint8 frame into 80x80 2D image
    Source: https://gist.github.com/karpathy/a4166c7fe253700972fcbc77e4ea32c5)
    """
    image = image[0:160]  # crop
    image = image[::2, ::2, 0]  # downsample by factor of 2
    #image[image == 144] = 0  # erase background (background type 1)
    #image[image == 109] = 0  # erase background (background type 2)
    #image[image != 0] = 1  # everything else (paddles, ball) just set to 1
    #print(image.shape)
    return np.reshape(image, pong_inputdim)

prepro(observation)

def discount_rewards(r, gamma=0.99):
    """ take 1D float array of rewards and compute discounted reward
    Source: https://gist.github.com/karpathy/a4166c7fe253700972fcbc77e4ea32c5)
    """
    discounted_r = np.zeros_like(r)
    running_add = 0
    for t in reversed(range(0, len(r))):
        if r[t] != 0:
            running_add = 0  # reset the sum, since this was a game boundary (pong specific!)
        running_add = running_add * gamma + r[t]
        discounted_r[t] = running_add

    # standardize the rewards to be unit normal (helps control the gradient estimator variance)
    discounted_r -= np.mean(discounted_r)
    discounted_r /= np.std(discounted_r) + eps
    #import matplotlib.pyplot as plt; plt.plot(discounted_r); plt.show()
    return discounted_r


class Policy(nn.Module):
    """Pytorch CNN implementing a Policy"""
    def __init__(self):
        super(Policy, self).__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=5, stride=2)
        self.bn1 = nn.BatchNorm2d(16)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=5, stride=2)
        self.bn2 = nn.BatchNorm2d(32)
        self.conv3 = nn.Conv2d(32, 32, kernel_size=5, stride=2)
        self.bn3 = nn.BatchNorm2d(32)
        self.head = nn.Linear(1568, pong_actions)

        self.saved_log_probs = []

    def forward(self, x):
        x = F.relu(self.bn1((self.conv1(x))))
        x = F.relu(self.bn2((self.conv2(x))))
        x = F.relu(self.bn3((self.conv3(x))))
        return F.softmax(self.head(x.view(x.size(0), -1)), dim=1)

    def select_action(self, state):
        state = state.float().unsqueeze(0)
        probs = self(state)
        m = Categorical(probs)
        action = m.sample()
        self.saved_log_probs.append(m.log_prob(action))
        return action.item()

observation = env.reset()
curx = prepro(observation)
prevx = None
x = curx - prevx if prevx is not None else np.zeros(pong_inputdim)
x = torch.tensor(x).to(device)
policy = Policy()
action = policy.select_action(x)

def runepisode(env, policy, steps=2000, render=False):
    observation = env.reset()
    curx = prepro(observation)
    prevx = None
    observations = []
    rewards = []
    rawframes = []

    for _ in range(steps):
        if render:
            env.render()
        x = curx - prevx if prevx is not None else np.zeros(pong_inputdim)
        x = torch.tensor(x).to(device)
        action = policy.select_action(x)
        observation, reward, done, info = env.step(action)
        prevx = curx
        curx = prepro(observation)
        observations.append(x)
        rewards.append(reward)
        rawframes.append(observation)
        if done:
            break

    return rewards, observations, rawframes


def saveanimation(rawframes, filename):
    """Saves a sequence of frames as an animation
    The filename must include an appropriate video extension
    """
    clip = mpy.ImageSequenceClip(rawframes, fps=60)
    clip.write_videofile(filename)

def train(env,render=False,checkpoint='/content/drive/My Drive/Colab Notebooks/RL/proj4/code/policygradient.pt', saveanimations=False):
    env=env
    try:
        policy = torch.load(checkpoint)
        print("Resumed checkpoint {}".format(checkpoint))
    except:
        policy = Policy()
        print("Created policy network from scratch")
    print(policy)
    policy.to(device)
    print("device: {}".format(device))
    optimizer = optim.RMSprop(policy.parameters(), lr=1e-4)

    episode = 0
    AllScores=[]
    AvgRewards=[]
    best_reward=None
    while episode<80000:
        # Gather samples
        rewards, observations, rawframes = runepisode(env, policy, render=render)
        
        drewards = discount_rewards(rewards)
        # Update policy network
        policy_loss = [-log_prob * reward for log_prob, reward in zip(policy.saved_log_probs, drewards)]
        optimizer.zero_grad()
        policy_loss = torch.cat(policy_loss).sum()
        policy_loss.backward()
        optimizer.step()
        del policy.saved_log_probs[:]
        EpisodeScore=np.sum(rewards)
        episode += 1
        # Save policy network from time to time
        AllScores.append(EpisodeScore)
        meanScore = np.mean(AllScores[-30:])#100
        AvgRewards.append(meanScore)
        if(episode%50==0):
          print("Total reward for episode {}: {}, mean score: {}".format(episode, np.sum(rewards),meanScore))
        if best_reward is None or best_reward < meanScore:
                    torch.save(policy, checkpoint)    
                    if best_reward is not None:
                        print("Best mean reward updated %.3f -> %.3f, model saved" % (best_reward, meanScore))
                        best_reward = meanScore
                        saveanimation(rawframes, "{}_episode{}best.mp4".format(checkpoint, episode))

        if(episode%500==0):
                 plt.figure(2)
                 plt.clf()
                 plt.xlabel('Episode')
                 plt.ylabel('Average Reward over 30 episodes')
                 plt.title('Average Reward vs Episode')
                 plt.plot( np.linspace(1,episode,episode),AvgRewards)
                 plt.savefig('/content/drive/My Drive/Colab Notebooks/RL/proj4/code/plots/' + str(episode) +'.png')
                 saveanimation(rawframes, "{}_episode{}.mp4".format(checkpoint, episode))
        #if(episode%5000==0):
         #        policy = torch.load(checkpoint)

        
        #if not episode % 50:
        #    torch.save(policy, checkpoint)
        # Save animation (if requested)
        #if saveanimations:
        #    saveanimation(rawframes, "{}_episode{}.mp4".format(checkpoint, episode))

if __name__ == "__main__":
    screen_width, screen_height = 160, 160
    config = {
                "offscreen_rendering": True,
                "observation": {
                "type": "GrayscaleObservation",
                "weights": [0.2989, 0.5870, 0.1140],  # weights for RGB conversion
                "stack_size": 4,
                "observation_shape": (screen_width, screen_height)
                },
                "screen_width": screen_width,
              "screen_height": screen_height,
              "scaling": 5.75,
              "policy_frequency": 2,
              "action": {
                  "type": "DiscreteMetaAction"
              },
            'duration': 3000,
            'offroad_terminal':True,
            'policy_frequency':10,
            'simulation_frequency':10,
            'vehicles_count':20,
            }
    env = gym.make('highway-v0')
    env.configure(config)
    train(env,render=True, saveanimations=True)
