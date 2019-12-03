#-*- coding:utf-8 -*-
# This sample uses a Caffe ResNet50 Model to create a TensorRT Inference Engine
import random
from PIL import Image
import numpy as np

import pycuda.driver as cuda
# This import causes pycuda to automatically manage CUDA context creation and cleanup.
import pycuda.autoinit

import tensorrt as trt

import sys, os
sys.path.insert(1, os.path.join(sys.path[0], ".."))
import common

class ModelData(object):
    MODEL_PATH = "car_rec.caffemodel"
    DEPLOY_PATH = "car_rec.prototxt"
    LABEL_PATH = "model_name.txt"
    INPUT_SHAPE = (3, 224, 224)
    OUTPUT_NAME = "prob"
    # We can convert TensorRT data types to numpy types with trt.nptype()
    DTYPE = trt.float32

# You can set the logger severity higher to suppress messages (or lower to display more messages).
TRT_LOGGER = trt.Logger(trt.Logger.WARNING)

# Allocate host and device buffers, and create a stream.
def allocate_buffers(engine):
    # Determine dimensions and create page-locked memory buffers (i.e. won't be swapped to disk) to hold host inputs/outputs.
    h_input = cuda.pagelocked_empty(trt.volume(engine.get_binding_shape(0)), dtype=trt.nptype(ModelData.DTYPE))
    h_output = cuda.pagelocked_empty(trt.volume(engine.get_binding_shape(1)), dtype=trt.nptype(ModelData.DTYPE))
    # Allocate device memory for inputs and outputs.
    d_input = cuda.mem_alloc(h_input.nbytes)
    d_output = cuda.mem_alloc(h_output.nbytes)
    # Create a stream in which to copy inputs/outputs and run inference.
    stream = cuda.Stream()
    return h_input, d_input, h_output, d_output, stream

def do_inference(context, h_input, d_input, h_output, d_output, stream):
    # Transfer input data to the GPU.
    cuda.memcpy_htod_async(d_input, h_input, stream)
    # Run inference.
    context.execute_async(bindings=[int(d_input), int(d_output)], stream_handle=stream.handle)
    # Transfer predictions back from the GPU.
    cuda.memcpy_dtoh_async(h_output, d_output, stream)
    # Synchronize the stream
    stream.synchronize()

# The Caffe path is used for Caffe2 models.
def build_engine_caffe(model_file, deploy_file, engine_file_path=""):
	# # You can set the logger severity higher to suppress messages (or lower to display more messages).
	# with trt.Builder(TRT_LOGGER) as builder, builder.create_network() as network, trt.CaffeParser() as parser:
	#     # Workspace size is the maximum amount of memory available to the builder while building an engine.
	#     # It should generally be set as high as possible.
	#     builder.max_workspace_size = common.GiB(1)
	#     # Load the Caffe model and parse it in order to populate the TensorRT network.
	#     # This function returns an object that we can query to find tensors by name.
	#     model_tensors = parser.parse(deploy=deploy_file, model=model_file, network=network, dtype=ModelData.DTYPE)
	#     # For Caffe, we need to manually mark the output of the network.
	#     # Since we know the name of the output tensor, we can find it in model_tensors.
	#     network.mark_output(model_tensors.find(ModelData.OUTPUT_NAME))
	#     return builder.build_cuda_engine(network)
	def build_engine():
	    with trt.Builder(TRT_LOGGER) as builder, builder.create_network() as network, trt.CaffeParser() as parser:
	        builder.fp16_mode = True
	        builder.strict_type_constraints = True
	        builder.max_batch_size = 4
	        # Workspace size is the maximum amount of memory available to the builder while building an engine.
	        # It should generally be set as high as possible.
	        builder.max_workspace_size = common.GiB(1)
	        # Load the Caffe model and parse it in order to populate the TensorRT network.
	        # This function returns an object that we can query to find tensors by name.
	        model_tensors = parser.parse(deploy=deploy_file, model=model_file, network=network, dtype=ModelData.DTYPE)
	        # For Caffe, we need to manually mark the output of the network.
	        # Since we know the name of the output tensor, we can find it in model_tensors.
	        network.mark_output(model_tensors.find(ModelData.OUTPUT_NAME))
	        engine = builder.build_cuda_engine(network)
	        with open(engine_file_path, "wb") as f:
	            f.write(engine.serialize())
	        return engine
	if os.path.exists(engine_file_path):
		print("Reading engine from file {}".format(engine_file_path))
		with open(engine_file_path, 'rb') as f, trt.Runtime(TRT_LOGGER) as runtime:
			engine = runtime.deserialize_cuda_engine(f.read())
			return engine
	else:
		build_engine()


def load_normalized_test_case(test_image, pagelocked_buffer):
    # Converts the input image to a CHW Numpy array
    def normalize_image(image):
        # Resize, antialias and transpose the image to CHW.
        c, h, w = ModelData.INPUT_SHAPE
        return np.asarray(image.resize((w, h), Image.ANTIALIAS)).transpose([2, 0, 1]).astype(trt.nptype(ModelData.DTYPE)).ravel()

    # Normalize the image and copy to pagelocked memory.
    np.copyto(pagelocked_buffer, normalize_image(Image.open(test_image)))
    return test_image

def load_normalized_test_cases(test_image_list, inputs):
    def normalize_image(image):
        # Resize, antialias and transpose the image to CHW.
        c, h, w = ModelData.INPUT_SHAPE
        return np.asarray(image.resize((w, h), Image.ANTIALIAS)).transpose([2, 0, 1]).astype(trt.nptype(ModelData.DTYPE)).ravel()
    normalized_img_list = []
    for test_image in test_image_list:
    	normalized_img_list.append(normalize_image(Image.open('car_rec_test/'+test_image)))
    	pass
    # print(len(normalized_img_list))
    # print(normalized_img_list)
    # print(np.array(normalized_img_list))
    # print(np.array(normalized_img_list).ravel())
    inputs[0].host = np.array(normalized_img_list).ravel()
    # np.copyto(inputs[0].host, np.array(normalized_img_list).ravel())
    return test_image_list  

def main():
    # Set the data path to the directory that contains the trained models and test images for inference.
    # data_path, data_files = common.find_sample_data(description="Runs a ResNet50 network with a TensorRT inference engine.", subfolder="resnet50", find_files=["binoculars.jpeg", "reflex_camera.jpeg", "tabby_tiger_cat.jpg", ModelData.MODEL_PATH, ModelData.DEPLOY_PATH, "class_labels.txt"])
    # Get test images, models and labels.
    # test_images = data_files[0:3]
    # test_image = "0.jpg"
    test_image_list = os.listdir('car_rec_test')
    print(test_image_list)
    engine_file_path = "car_rec.trt"
    caffe_model_file, caffe_deploy_file, labels_file = [ModelData.MODEL_PATH, ModelData.DEPLOY_PATH, ModelData.LABEL_PATH]
    labels = open(labels_file, 'r').read().split('\n')

    # Build a TensorRT engine.
    with build_engine_caffe(caffe_model_file, caffe_deploy_file, engine_file_path) as engine:
        # Inference is the same regardless of which parser is used to build the engine, since the model architecture is the same.
        # Allocate buffers and create a CUDA stream.
        # h_input, d_input, h_output, d_output, stream = allocate_buffers(engine)
        inputs, outputs, bindings, stream = common.allocate_buffers(engine)
        # Contexts are used to perform inference.
        with engine.create_execution_context() as context:
            # Load a normalized test case into the host input page-locked buffer.
            # test_image = random.choice(test_images)
            # test_case = load_normalized_test_case(test_image, h_input)
            test_cases = load_normalized_test_cases(test_image_list, inputs)
            # Run the engine. The output will be a 1D tensor of length 1000, where each value represents the
            # probability that the image corresponds to that label
            # do_inference(context, h_input, d_input, h_output, d_output, stream)
            trt_outputs = common.do_inference(context, bindings, inputs, outputs, stream, 4)
            outs = trt_outputs[0].reshape(4,427)
            # print(outs)
            for x in range(0,len(outs)):
            	pred = labels[np.argmax(outs[x])]
            	print(pred)
            	pass
            # print(trt_outputs)
            # print(len(trt_outputs))
            # print(type(trt_outputs))
            # print(len(trt_outputs[0]))
            

            # We use the highest probability as our prediction. Its index corresponds to the predicted label.
            # print(h_output)
            # pred = labels[np.argmax(h_output)]
            # print(pred)
            # if "_".join(pred.split()) in os.path.splitext(os.path.basename(test_case))[0]:
            #     print("Correctly recognized " + test_case + " as " + pred)
            # else:
            #     print("Incorrectly recognized " + test_case + " as " + pred)

if __name__ == '__main__':
    main()
