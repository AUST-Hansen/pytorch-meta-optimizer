import argparse
import operator
import sys

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from data import get_batch
from meta_optimizer import MetaModel, MetaOptimizer
from model import Model
from torch.autograd import Variable

parser = argparse.ArgumentParser(description='PyTorch REINFORCE example')
parser.add_argument('--batch_size', type=int, default=16, metavar='N',
                    help='batch size (default: 16)')
parser.add_argument('--optimizer_steps', type=int, default=20, metavar='N',
                    help='number of meta optimizer steps (default: 20)')
parser.add_argument('--truncated_bptt_step', type=int, default=10, metavar='N',
                    help='step at which it truncates bptt (default: 10)')
parser.add_argument('--updates_per_epoch', type=int, default=100, metavar='N',
                    help='updates per epoch (default: 100)')
parser.add_argument('--max_epoch', type=int, default=100, metavar='N',
                    help='number of epoch (default: 100)')
parser.add_argument('--hidden_size', type=int, default=10, metavar='N',
                    help='hidden size of the meta optimizer (default: 10)')
args = parser.parse_args()

assert args.optimizer_steps % args.truncated_bptt_step == 0

# Create a meta optimizer that wraps a model into a meta model
# to keep track of the meta updates.
meta_optimizer = MetaOptimizer(MetaModel(Model()), args.hidden_size)
optimizer = optim.Adam(meta_optimizer.parameters(), lr=1e-3)
loss_fn = lambda f_x, y: (f_x - y).pow(2).mean()

for epoch in range(args.max_epoch):
    decrease_in_loss = 0.0
    for i in range(args.updates_per_epoch):

        # Sample a new model
        model = Model()

        x, y = get_batch(args.batch_size)
        x, y = Variable(x), Variable(y)

        # Compute initial loss of the model
        f_x = model(x)
        initial_loss = loss_fn(f_x, y)

        for k in range(args.optimizer_steps // args.truncated_bptt_step):
            # Keep states for truncated BPTT
            meta_optimizer.reset_lstm(keep_states=k > 0, model=model)

            loss_sum = 0
            for j in range(args.truncated_bptt_step):
                x, y = get_batch(args.batch_size)
                x, y = Variable(x), Variable(y)

                # First we need to compute the gradients of the model
                f_x = model(x)
                loss = loss_fn(f_x, y)
                model.zero_grad()
                loss.backward()

                # Perfom a meta update using gradients from model
                # and return the current meta model saved in the optimizer
                meta_model = meta_optimizer.meta_update(model)

                # Compute a loss for a step the meta optimizer
                f_x = meta_model(x)
                loss = loss_fn(f_x, y)
                loss_sum += loss

            # Update the parameters of the meta optimizer
            meta_optimizer.zero_grad()
            loss_sum.backward()
            optimizer.step()

        # Compute relative decrease in the loss function w.r.t initial value
        decrease_in_loss += loss.data[0] / initial_loss.data[0]

    print("Epoch: {}, average final/initial loss ratio: {}".format(epoch,
                                                                   decrease_in_loss / args.updates_per_epoch))
