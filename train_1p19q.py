import os
import numpy as np
import copy
import math
import matplotlib.pyplot as plt
from sklearn.utils import class_weight

import argparse

from keras.models import load_model
from keras.preprocessing.image import ImageDataGenerator
from keras import optimizers, losses
from keras.models import Sequential, Model, clone_model
from keras.layers import Dropout, Flatten, Dense, GlobalAveragePooling2D, AveragePooling2D
from keras import backend as k 
from keras.callbacks import ModelCheckpoint, LearningRateScheduler, TensorBoard, EarlyStopping , Callback

# modify last layer
def update_the_last_layer(base_model, nb_classes):
	# remove the FC layer of the base model
	base_model.layers.pop()
	# # remove the flattening layer
	# base_model.layers.pop()
	# # remove the average pooling layer
	# base_model.layers.pop()
	# obtain the last layer after removing. It should be a merge layer
	last_layer = base_model.layers[-1]
	x = last_layer.output
	# # pool the layer
	# x = AveragePooling2D()(x)
	# add FC layer with size of FC_size
	x = Dropout(0.7)(x)
	x = Dense(nb_classes, activation = 'sigmoid')(x)
	
	model = Model(input=base_model.input, output=x)
	return model

# By default, using Adam
def setup_optimizer(learning_rate=0.0001): #learning rate needs to be tuned
	beta_1 = 0.9 #d_w: a momentum like term
	beta_2 = 0.999 # d_w^2 
	epsilon = 1e-8 # no need to tune
	Adam = optimizers.Adam(lr = learning_rate, beta_1 = beta_1, beta_2 = beta_2, epsilon = epsilon)
	return Adam

def setup_to_transfer_learn(model, base_model, optimizer):
	"""Freeze all layers and compile the model"""
	for layer in base_model.layers:
		layer.trainable = False

	model.compile(optimizer=optimizer,loss='binary_crossentropy', metrics=['accuracy'])

def setup_to_finetune(model, optimizer):
	"""Freeze all the layers but top 1 conv layers. 8 layers can be trained in this case
	
	Args:
		model: keras model
		optimizer: keras optimizer
	"""
	for layer_ind in range(-3,-12,-1):
		model.layers[layer_ind].trainable = True

	model.compile(optimizer=optimizer,loss='binary_crossentropy', metrics=['accuracy'])


class LossHistory(Callback):
	def on_train_begin(self, logs={}):
	   self.losses = []
	   self.lr = []
 
	def on_epoch_end(self, batch, logs={}):
	   self.losses.append(logs.get('loss'))
	   self.lr.append(step_decay(len(self.losses)))

def step_decay(epoch, learning_rate, decay_rate=0.25, epochs_drop=10.0):
	# for every 20 epoches, decay the learning rate
	lrate = learning_rate * math.pow(decay_rate,
		math.floor((1+epoch)/epochs_drop))
	return lrate

def calculate_class_weight(train_label):
	class_weight_dict = dict(enumerate(class_weight.compute_class_weight('balanced', np.unique(train_label), train_label)))

	return class_weight_dict


#Specify which GPU to be used
os.environ["CUDA_VISIBLE_DEVICES"]="0"

seed = 0
# load training and validation data
train_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted_balanced_20/train/'
val_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted_balanced_20/val/'

os.chdir(train_dir)
train_FLAIR = np.load('train_FLAIR.npy')
train_1p19q = np.load('train_1p19q.npy') # 27 1s, 273 0s.

os.chdir(val_dir)
val_FLAIR = np.load('val_FLAIR.npy')
val_1p19q = np.load('val_1p19q.npy')


# Augment train data
train_datagen =  ImageDataGenerator(
	featurewise_center = True,
	featurewise_std_normalization = True,
	rotation_range=30,
	width_shift_range=0.2,
	height_shift_range=0.2,
	shear_range=0.2,
	zoom_range=0.2,
	horizontal_flip=True,
	vertical_flip=True
)

# Val data stays the same
val_datagen = ImageDataGenerator(
	# featurewise_center = True,
	# featurewise_std_normalization = True,
	# rotation_range=30,
	# width_shift_range=0.2,
	# height_shift_range=0.2,
	# shear_range=0.2,
	# zoom_range=0.2,
	# horizontal_flip=True,
	# vertical_flip=True
)

# compute quantities required for featurewise normalization such as mean, std, etc.
train_datagen.fit(train_FLAIR)
# val_datagen.fit(val_FLAIR)

# specify the directory to save images
# train_aug_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted/aug_train/'
# val_aug_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted/aug_val/'

train_generator = train_datagen.flow(
	x = train_FLAIR,
	y = train_1p19q,
	shuffle = True,
	batch_size = 64
	# save_to_dir = train_aug_dir
)
val_generator = val_datagen.flow(
	x = val_FLAIR,
	y = val_1p19q,
	shuffle = True,
	batch_size = 64
	# save_to_dir = val_aug_dir
)
# load models
os.chdir('/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/1p_19q/glioma_models')
model_FLAIR = load_model('FLAIR_model.h5')
# model_T2 = load_model('T2_model.h5')
# model_T1 = load_model('T1_model.h5')
# model_T1post = load_model('T1post_model.h5')
n_epoch = 40

base_model = model_FLAIR

# reset the last fully connected laer
model = update_the_last_layer(base_model = base_model, nb_classes=1)

# set up optimizer
optimizer = setup_optimizer(learning_rate=0.00001)

# set up the transfer learning
setup_to_transfer_learn(model = model, base_model = base_model, optimizer = optimizer)

# set up the fine-tuning
setup_to_finetune(model = model, optimizer = optimizer)

loss_history = LossHistory()
learning_rate = LearningRateScheduler(step_decay, verbose = 1)
callbacks_list = [loss_history, learning_rate]

# compute the class weight
class_weight_dict = calculate_class_weight(train_1p19q)

history_transfer = model.fit_generator(
	generator = train_generator,
	epochs = 40,
	verbose = 1,
	callbacks = callbacks_list,
	validation_data = val_generator,
	shuffle = True,
	class_weight = class_weight_dict)

output_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted_balanced_20/outputs/'
os.chdir(output_dir)
np.save('flair_history_conv2', history_transfer.history)
model.save('flair_model_conv2.h5')

# load test data
test_dir = '/rsrch1/bcb/Imaging-Genomics_SIBL/DONNIE_KIM/Brachy_deep_learning/IDH_Prediction/data/data_splitted_balanced_20/test/'
os.chdir(test_dir)
test_FLAIR = np.load('test_FLAIR.npy')
test_1p19q = np.load('test_1p19q.npy') # 27 1s, 273 0s.

#predict
score = model.evaluate(test_FLAIR,test_1p19q,batch_size=64)


if __name__="__main":
	parser = argparse.ArgumentParser(description = "Run ResNet-34 transfer learning for 1p/19q classification")

	partse.add_argument('--gpus_vis', nargs='?', metavar='gpus_visible', help = "GPU number that is present to the model. Default is 0.", 
						type = str, default = "0", required = False)
	
	parser.add_argument('--modelname', type = str, help = "Name of the model", required = True)

	parser.add_argument("--train_dir", type = str, help = "Provide absolute path to the training directory", required = True)

	parser.add_argument("--val_dir", type = str, help = "Provide absolute path to the validation directory", required = True)
	
	a.add_argument("--nb_epoch", default=NB_EPOCHS)
	a.add_argument("--batch_size", default=BAT_SIZE)
	a.add_argument("--output_model_file", default="inceptionv3-ft.model")
	a.add_argument("--plot", action="store_true")

	args = a.parse_args()
	if args.train_dir is None or args.val_dir is None:
	a.print_help()
	sys.exit(1)

	if (not os.path.exists(args.train_dir)) or (not os.path.exists(args.val_dir)):
	print("directories do not exist")
	sys.exit(1)