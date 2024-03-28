# -*- coding: utf-8 -*-
"""
Integrate a model with the DEEP API
"""

import json
import argparse
import pkg_resources
import os
import re
import pickle  # nosec
import time

import neural_transfer.config as cfg
import neural_transfer.models.utils as iutils
import neural_transfer.models.file_utils as futils
from neural_transfer.models.transformer_net import TransformerNet
from neural_transfer.models.vgg import Vgg16 

import torch
import numpy as np
from torch.optim import Adam
from torch.utils.data import DataLoader
from torchvision import datasets
from torchvision import transforms
import torchvision.models as models

from PIL import Image
from aiohttp.web import HTTPBadRequest

from flaat import Flaat
#from __future__ import print_function
flaat = Flaat()

#def _catch_error(f):
#    def wrap(*args, **kwargs):
#        try:
#            return f(*args, **kwargs)
#        except Exception as e:
#            raise HTTPBadRequest(reason=e)


def _fields_to_dict(fields_in):
    """
    Example function to convert mashmallow fields to dict()
    """
    dict_out = {}
    
    for key, val in fields_in.items():
        param = {}
        param['default'] = val.missing
        param['type'] = type(val.missing)
        if key == 'files' or key == 'urls':
            param['type'] = str

        val_help = val.metadata['description']
        if 'enum' in val.metadata.keys():
            val_help = "{}. Choices: {}".format(val_help, 
                                                val.metadata['enum'])
        param['help'] = val_help

        try:
            val_req = val.required
        except:
            val_req = False
        param['required'] = val_req

        dict_out[key] = param
    return dict_out

def get_metadata():
    """
    Function to read metadata
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_metadata
    :return:
    """

    module = __name__.split('.', 1)

    try:
        pkg = pkg_resources.get_distribution(module[0])
    except pkg_resources.RequirementParseError:
        # if called from CLI, try to get pkg from the path
        distros = list(pkg_resources.find_distributions(cfg.BASE_DIR, 
                                                        only=True))
        if len(distros) == 1:
            pkg = distros[0]
    except Exception as e:
        raise HTTPBadRequest(reason=e)

    ### One can include arguments for train() in the metadata
    train_args = _fields_to_dict(get_train_args())
    # make 'type' JSON serializable
    for key, val in train_args.items():
        train_args[key]['type'] = str(val['type'])

    ### One can include arguments for predict() in the metadata
    predict_args = _fields_to_dict(get_predict_args())
    # make 'type' JSON serializable
    for key, val in predict_args.items():
        predict_args[key]['type'] = str(val['type'])

    models_names = iutils.get_models()
    models = ['mosaic', 'udnie', 'candy', 'rain_princess']
    models = models + models_names
    meta = {
        'name': None,
        'models': models,
        'version': None,
        'summary': None,
        'home-page': None,
        'author': None,
        'author-email': None,
        'license': None,
        #'help-train' : train_args,
        #'help-predict' : predict_args
    }

    for line in pkg.get_metadata_lines("PKG-INFO"):
        line_low = line.lower() # to avoid inconsistency due to letter cases
        for par in meta:
            if line_low.startswith(par.lower() + ":"):
                _, value = line.split(": ", 1)
                meta[par] = value

    return meta


def warm():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.warm
    :return:
    """
    # e.g. prepare the data


def get_predict_args():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_predict_args
    :return:
    """
    return cfg.PredictArgsSchema().fields


#@_catch_error
def predict(**kwargs):
    """
    Function to execute prediction
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.predict
    :param kwargs:
    :return:
    """    
    if (kwargs['img_content'] is not None) and (kwargs['model_name'] is not None):
        return _predict_data(kwargs)
    else:
        raise "[ERROR] Please select a style and a content image."
    
def _predict_data(args):
    """
    (Optional) Helper function to make prediction on an uploaded file
    """       
    # defining paths to save the images.
    content_img_path = os.path.join(cfg.DATA_DIR, 'content_image.png')
    result_img_path = os.path.join(cfg.DATA_DIR, 'result_image.png')
    
    # select wether cpu or gpu.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("[INFO] Running in device: {}".format(device))
    
    #Download weight files and model from nextcloud if necessary.
    if args['model_name'] in ['mosaic', 'udnie', 'candy', 'rain_princess']:
        status_weights, _ = iutils.download_pred_model(args['model_name'])
    else:
        iutils.download_model(args['model_name'])
    
    nums = [cfg.MODEL_DIR, args['model_name']]
    model_path = '{0}/{1}.pth'.format(*nums)
    
    if not(os.path.exists(model_path)):
        raise "[ERROR] The name of the model does not exist. Please write an existing model name."
    
    # image content tmp path.
    img_content_tmp_path = args["img_content"].filename
    cnt = Image.open(img_content_tmp_path)
    cnt.save(content_img_path)

    content_image = iutils.load_image(img_content_tmp_path)
    content_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Lambda(lambda x: x.mul(255))
    ])
    content_image = content_transform(content_image)
    content_image = content_image.unsqueeze(0).to(device)
    
    with torch.no_grad():
        style_model = TransformerNet()
        state_dict = torch.load(model_path)
        # remove saved deprecated running_* keys in InstanceNorm from the checkpoint
        for k in list(state_dict.keys()):
            if re.search(r'in\d+\.running_(mean|var)$', k):
                del state_dict[k]
        style_model.load_state_dict(state_dict)
        style_model.to(device)
        output = style_model(content_image).cpu()
            
    iutils.save_image(result_img_path, output[0])    

    # return an image.
    if(args['accept'] == 'image/png'):
        message = open(result_img_path, 'rb')
        
    #return a pdf.
    else:
        #Resizing images for thw pdf file.
        futils.merge_images()

        #Create the PDF file.
        result_pdf = futils.create_pdf()
        message = open(result_pdf, 'rb')
        
    print("[INFO] Transferring finished.")
     
    return message


def _predict_url(args):
    """
    (Optional) Helper function to make prediction on an URL
    """
    message = 'Not implemented (predict_url())'
    message = {"Error": message}
    return message


def get_train_args():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_train_args
    :param kwargs:
    :return:
    """
    return cfg.TrainArgsSchema().fields


###
# @flaat.login_required() line is to limit access for only authorized people
# Comment this line, if you open training for everybody
# More info: see https://github.com/indigo-dc/flaat
###
#@flaat.login_required() # Allows only authorized people to train
def train(**kwargs):
    """
    Train network
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/latest/user/v2-api.html#deepaas.model.v2.base.BaseModel.train
    :param kwargs:
    :return:
    """

    message = { "status": "ok",
                "training": [],
              }
    
    # 1. implement your training here. 
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("[INFO] Running in device: {}".format(device))

    np.random.seed(1234)
    torch.manual_seed(4321)

    transform = transforms.Compose([
        transforms.Resize(512),
        transforms.CenterCrop(512),
        transforms.ToTensor(),
        transforms.Lambda(lambda x: x.mul(255))
    ])

    # download style image.
    iutils.download_style_image(kwargs["model_name"])

    # download training dataset.
    iutils.download_dataset()
    
    # loading dataset into Dataloader
    train_dataset = datasets.ImageFolder(cfg.DATA_DIR, transform)  #folder
    train_loader = DataLoader(train_dataset, batch_size=kwargs["batch_size"])

    transformer = TransformerNet().to(device)
    optimizer = Adam(transformer.parameters(), kwargs["learning_rate"])
    mse_loss = torch.nn.MSELoss()

    vgg = Vgg16(requires_grad=False).to(device)
    style_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Lambda(lambda x: x.mul(255))
    ])
    
    img_style = os.path.join(cfg.DATA_DIR, kwargs["model_name"])

    style = iutils.load_image(img_style, size=kwargs["size_train_img"])
    style = style_transform(style)
    style = style.repeat(kwargs["batch_size"], 1, 1, 1).to(device)

    features_style = vgg(iutils.normalize_batch(style))
    gram_style = [iutils.gram_matrix(y) for y in features_style]
    
    print("[INFO] Starting training...")


    for e in range(kwargs["epochs"]):
        transformer.train()
        agg_content_loss = 0.
        agg_style_loss = 0.
        count = 0
        for batch_id, (x, _) in enumerate(train_loader):
            n_batch = len(x)
            count += n_batch
            optimizer.zero_grad()

            x = x.to(device)
            y = transformer(x)

            y = iutils.normalize_batch(y)
            x = iutils.normalize_batch(x)

            features_y = vgg(y)
            features_x = vgg(x)

            content_loss = kwargs["content_weight"]* mse_loss(features_y.relu2_2, features_x.relu2_2)

            style_loss = 0.
            for ft_y, gm_s in zip(features_y, gram_style):
                gm_y = iutils.gram_matrix(ft_y)
                style_loss += mse_loss(gm_y, gm_s[:n_batch, :, :])
            style_loss *= kwargs["style_weight"]

            total_loss = content_loss + style_loss
            total_loss.backward()
            optimizer.step()

            agg_content_loss += content_loss.item()
            agg_style_loss += style_loss.item()

            if (batch_id + 1) % kwargs["log_interval"] == 0:
                mesg = "{}\tEpoch {}:\t[{}/{}]\tcontent: {:.6f}\tstyle: {:.6f}\ttotal: {:.6f}".format(
                    time.ctime(), e + 1, count, len(train_dataset),
                                  agg_content_loss / (batch_id + 1),
                                  agg_style_loss / (batch_id + 1),
                                  (agg_content_loss + agg_style_loss) / (batch_id + 1)
                )
                print(mesg)
                
    
    print("[INFO] Transferring finished.")

    # save model.
    transformer.eval().cpu()
    head, sep, tail = kwargs["model_name"].partition('.')
    nums = [cfg.MODEL_DIR, head]
    save_model_path = '{0}/{1}.pth'.format(*nums)
    torch.save(transformer.state_dict(), save_model_path)
    
    # upload to nextcloud.
    if (kwargs['upload_model'] == True):
        #copy model weigths, classes to nextcloud.
        dest_dir = cfg.REMOTE_MODELS_DIR
        print("[INFO] Upload %s to %s" % (save_model_path, dest_dir))
        
        #uploading weights to nextcloud.
        iutils.upload_model(save_model_path)
        print("[INFO] Model uploaded.")

    print("[INFO] Trained model saved at", save_model_path)

    # 2. update "message"
    train_results = {"Total loss" : (agg_content_loss + agg_style_loss) / (batch_id + 1),
                     "Content loss": agg_content_loss / (batch_id + 1),
                     "Style loss":agg_style_loss / (batch_id + 1) } 
    
    message["training"].append(train_results)

    return message


# during development it might be practical 
# to check your code from CLI (command line interface)
def main():
    """
    Runs above-described methods from CLI
    (see below an example)
    """

    if args.method == 'get_metadata':
        meta = get_metadata()
        print(json.dumps(meta))
        return meta      
    elif args.method == 'predict':
        # [!] you may need to take special care in the case of args.files [!]
        results = predict(**vars(args))
        print(json.dumps(results))
        return results
    elif args.method == 'train':
        results = train(**vars(args))
        print(json.dumps(results))
        return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Model parameters', 
                                     add_help=False)

    cmd_parser = argparse.ArgumentParser()
    subparsers = cmd_parser.add_subparsers(
                            help='methods. Use \"deep_api.py method --help\" to get more info', 
                            dest='method')

    ## configure parser to call get_metadata()
    get_metadata_parser = subparsers.add_parser('get_metadata', 
                                         help='get_metadata method',
                                         parents=[parser])                                      
    # normally there are no arguments to configure for get_metadata()

    ## configure arguments for predict()
    predict_parser = subparsers.add_parser('predict', 
                                           help='commands for prediction',
                                           parents=[parser]) 
    # one should convert get_predict_args() to add them in predict_parser
    # For example:
    predict_args = _fields_to_dict(get_predict_args())
    for key, val in predict_args.items():
        predict_parser.add_argument('--%s' % key,
                               default=val['default'],
                               type=val['type'],
                               help=val['help'],
                               required=val['required'])

    ## configure arguments for train()
    train_parser = subparsers.add_parser('train', 
                                         help='commands for training',
                                         parents=[parser]) 
    # one should convert get_train_args() to add them in train_parser
    # For example:
    train_args = _fields_to_dict(get_train_args())
    for key, val in train_args.items():
        train_parser.add_argument('--%s' % key,
                               default=val['default'],
                               type=val['type'],
                               help=val['help'],
                               required=val['required'])

    args = cmd_parser.parse_args()
    
    main()
