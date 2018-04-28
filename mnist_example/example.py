#pylint: disable=E1101,R,C
import numpy as np
import torch.nn as nn
from s2cnn.nn.soft.so3_conv import SO3Convolution
from s2cnn.nn.soft.s2_conv import S2Convolution
from s2cnn.nn.soft.so3_integrate import so3_integrate
from s2cnn.ops.so3_localft import near_identity_grid as so3_near_identity_grid
from s2cnn.ops.s2_localft import near_identity_grid as s2_near_identity_grid
import torch.nn.functional as F
import torch
import torch.utils.data as data_utils
import gzip, pickle
import numpy as np
from torch.autograd import Variable

MNIST_PATH =  "s2_mnist.gz"

DEVICE_ID = 0

NUM_EPOCHS = 20
BATCH_SIZE = 32
LEARNING_RATE = 5e-3

def load_data(path, batch_size):

    with gzip.open(path, 'rb') as f:
        dataset = pickle.load(f)

    train_data = torch.from_numpy(
        dataset["train"]["images"][:,None,:,:].astype(np.float32))
    train_labels = torch.from_numpy(
        dataset["train"]["labels"].astype(np.int64))

    mean = train_data.mean()
    stdv = train_data.std()

    train_dataset = data_utils.TensorDataset(train_data, train_labels)
    train_loader = data_utils.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    test_data = torch.from_numpy(
        dataset["test"]["images"][:,None,:,:].astype(np.float32))
    test_labels = torch.from_numpy(
        dataset["test"]["labels"].astype(np.int64))

    test_dataset = data_utils.TensorDataset(test_data, test_labels)
    test_loader = data_utils.DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

    return train_loader, test_loader, train_dataset, test_dataset


class S2ConvNet(nn.Module):

    def __init__(self):
        super(S2ConvNet, self).__init__()

        f1 = 20
        f2 = 40
        f_output = 10

        b_in = 30
        b_l1 = 10
        b_l2 = 6

        grid_s2 = s2_near_identity_grid()
        grid_so3 = so3_near_identity_grid()

        self.conv1 = S2Convolution(
            nfeature_in=1,
            nfeature_out=f1,
            b_in=b_in,
            b_out=b_l1,
            grid=grid_s2)

        self.conv2 = SO3Convolution(
            nfeature_in=f1,
            nfeature_out=f2,
            b_in=b_l1,
            b_out=b_l2,
            grid=grid_so3)

        self.out_layer = nn.Linear(f2, f_output)

    def forward(self, x):

        x = self.conv1(x)
        x = F.relu(x)
        x = self.conv2(x)
        x = F.relu(x)

        x = so3_integrate(x)

        x = self.out_layer(x)

        return x


def main():

    train_loader, test_loader, train_dataset, _ = load_data(
        MNIST_PATH, BATCH_SIZE)

    torch.cuda.set_device(DEVICE_ID)

    classifier = S2ConvNet()

    print("#params", sum([x.numel() for x in classifier.parameters()]))

    if torch.cuda.is_available():
        classifier.cuda(DEVICE_ID)

    criterion = nn.CrossEntropyLoss()
    if torch.cuda.is_available():
        criterion = criterion.cuda(DEVICE_ID)

    optimizer = torch.optim.Adam(
        classifier.parameters(),
        lr=LEARNING_RATE)

    for epoch in range(NUM_EPOCHS):
        for i, (images, labels) in enumerate(train_loader):
            images = Variable(images)
            labels = Variable(labels)

            if torch.cuda.is_available():
                images = images.cuda(DEVICE_ID)
                labels = labels.cuda(DEVICE_ID)

            optimizer.zero_grad()
            outputs = classifier(images)
            loss = criterion(outputs, labels)
            loss.backward()

            optimizer.step()

            print('\rEpoch [{0}/{1}], Iter [{2}/{3}] Loss: {4:.4f}'.format(
                epoch+1, NUM_EPOCHS, i+1, len(train_dataset)//BATCH_SIZE,
                loss.data[0]), end="")
        print("")
        correct = 0
        total = 0
        for i, (images, labels) in enumerate(test_loader):
            images = Variable(images, volatile=True)
            if torch.cuda.is_available():
                images = images.cuda(DEVICE_ID)
                labels = labels.cuda(DEVICE_ID)

            outputs = classifier(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum()

        print('Test Accuracy: {0}'.format(100 * correct / total))

if __name__ == '__main__':
    main()
