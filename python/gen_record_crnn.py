import os, re, logging, random
import codecs
import json
import glob
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import tensorflow as tf
from multiprocessing import Pool
import time
import tqdm
from Config import decode_sparse_tensor, sparse_tuple_from_label

import inception_preprocessing
from data_provider import preprocess_image

from utils import preprocess_train

from preprocessing import vgg_preprocessing


from utils import read_dict, reverse_dict, read_charset, CharsetMapper, decode_code, encode_code, is_valid_char

FLAGS = tf.app.flags.FLAGS

tf.app.flags.DEFINE_string('dict_text',
                           'resource/new_dic2.txt',
                           'absolute path of chinese dict txt')

tf.app.flags.DEFINE_string('dataset_dir',
                           'out',
                           'the dataset dir')

tf.app.flags.DEFINE_string('dataset_name',
                           'train',
                           'the dataset name')

tf.app.flags.DEFINE_integer('dataset_nums',
                            200,
                            'pre the dataset of nums')

tf.app.flags.DEFINE_string('output_dir',
                           'datasets/vgg_train',
                           'where to save the generated tfrecord file')

tf.app.flags.DEFINE_bool('test',
                         False,
                         'The test tf recored')

tf.app.flags.DEFINE_integer('thread',
                            10,
                            'the thread count')

tf.app.flags.DEFINE_string('suffix', 'png', 'suffix of image in data set')
tf.app.flags.DEFINE_string('height_and_width', '32,100', 'input size of each image in model training')
tf.app.flags.DEFINE_integer('length_of_text', 37, 'length of text when this text is padded')
tf.app.flags.DEFINE_integer('null_char_id', 133, 'the index of null char is used to padded text')


def _int64_feature(value):
    return tf.train.Feature(int64_list=tf.train.Int64List(value=value))


def _bytes_feature(value):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def encode_utf8_string(text, length, dic, null_char_id=133):
    """
    对于每一个text, 返回对应的 pad 型和 unpaded 型的真值, 即在chinese dict中的索引
    :return:
    """
    char_ids_padded = [null_char_id] * length
    char_ids_unpaded = [null_char_id] * len(text)
    for idx in range(len(text)):
        hash_id = dic[text[idx]]
        char_ids_padded[idx] = hash_id
        char_ids_unpaded[idx] = hash_id
    return char_ids_padded, char_ids_unpaded




def get_image_files2(image_dir, check=False):
    t = time.time()
    im_names = []  # glob.glob(os.path.join(image_dir, '*.{jpg,png,gif}'))
    for ext in ('*.png', '*.jpg', '*.gif'):
        im_names.extend(glob.glob(os.path.join(image_dir, ext)))
    chinese_dict = read_dict(FLAGS.dict_text)
    words = list(chinese_dict.keys())
    count = 0
    image_tupe = []
    for im_name in im_names:
        try:
            if not os.path.exists(im_name):
                continue
            if check:
                Image.open(im_name)
                # cv2.imread(fp)
            label = im_name.split('_')[1]
            if is_valid_char(label, words):
                os.remove(im_name)
                continue
            if len(label) == 0:
                os.remove(im_name)
                continue
            image_tupe.append((im_name, label))
            count += 1
        except Exception as e:
            print("fn:%s,error: %s", im_name, e)
            os.remove(im_name)
    te = time.time() - t
    print("cost time:%f, count:%d" % (te, len(image_tupe)))
    return image_tupe


def get_image_files(image_dir, check=False):
    t = time.time()
    chinese_dict = read_dict(FLAGS.dict_text)
    words = list(chinese_dict.keys())
    count = 0
    image_tupe = []
    for f in os.listdir(image_dir):
        try:
            if not f.endswith(('.gif', '.jpg', '.png')):
                continue
            fp = os.path.join(image_dir, f)
            if not os.path.isabs(fp):
                fp = os.path.abspath(fp)
            if not os.path.exists(fp):
                continue
            if check:
                Image.open(fp)
                # cv2.imread(fp)
            label = f.split('_')[1]
            if is_valid_char(label, words):
                os.remove(fp)
                continue
            if len(label) == 0:
                os.remove(fp)
                continue
            image_tupe.append((fp, label))
            count += 1
        except Exception as e:
            print("fn:%s,error: %s", fp, e)
            os.remove(fp)
    te = time.time() - t
    print("cost time:%f, count:%d" % (te, len(image_tupe)))
    return image_tupe


def make_tfrecord2(dict_chinese, dataset_name, shard_nums):
    """
    制作 tfrecord 文件
    :return:
    """
    if not os.path.exists(FLAGS.output_dir):
        os.makedirs(FLAGS.output_dir)

    image_tupe = get_image_files(FLAGS.dataset_dir)

    count = len(image_tupe)
    avg_num = int(count / shard_nums)
    if count % shard_nums != 0:
        avg_num = avg_num + 1
    print("avg_num: ", avg_num)

    vv_list = []
    for i in range(0, count, shard_nums):
        start = i
        end = i + shard_nums
        # print("start:%d-of-end:%d"%(start, end))
        filename = os.path.join(FLAGS.output_dir, dataset_name + '.tfrecords-%.5d-of-%.5d' % (start, end))
        # print('{} / {}, {}'.format(start, end, filename))
        vv = (image_tupe[start:end], filename, dict_chinese)
        vv_list.append(vv)
    done_list = []
    pool = Pool(FLAGS.thread)
    for _ in tqdm.tqdm(pool.imap_unordered(do_make_tfrecord, vv_list), total=len(vv_list)):
        done_list.append(_)
        pass
    pool.close()
    pool.join()

    print("done : ")
    for done in done_list:
        print(done)


def do_make_tfrecord(vv):
    image_tupe = vv[0]
    filename = vv[1]
    dict_chinese = vv[2]
    # print(image_tupe)
    # print("start:%d-of-end:%d" % (start, end))

    # 图片resize的高和宽
    split_results = FLAGS.height_and_width.split(',')
    height = int(split_results[0].strip())
    width = int(split_results[1].strip())

    tfrecord_writer = tf.python_io.TFRecordWriter(filename)

    for path_img, label in image_tupe:
        img = Image.open(path_img)
        if img.mode != "RGB":
            img = img.convert('RGB')
        if img.mode == "RGB":
            orig_width = img.size[0]
            orig_height = img.size[1]
            #img = img.resize((width, height), Image.NEAREST)
            if (orig_width != width) and (orig_height != height):
                img = img.resize((width, height), Image.ANTIALIAS)
            img_raw = img.tobytes()
            width, height = img.size
            channels = len(img.mode)
            char_ids = [chinese_dict[code] for code in label]
            indices, values, shapes = sparse_tuple_from_label([char_ids])
            example = tf.train.Example(
                features=tf.train.Features(feature={
                    "image": _bytes_feature(img_raw),
                    'text': _bytes_feature(encode_code(label)),
                    'width': _int64_feature([width]),
                    'height': _int64_feature([height]),
                    'channels': _int64_feature([channels]),
                    'orig_width': _int64_feature([orig_width]),
                    'format': _bytes_feature(b'raw'),
                    'char_ids': _int64_feature(char_ids),
                }))
            tfrecord_writer.write(example.SerializeToString())
    tfrecord_writer.close()
    return filename


def parse_tfrecord_file():
    # filename_queue = tf.train.string_input_producer([FLAGS.path_save_tfrecord])
    # 注，files 是一个local variable，不会保存到checkpoint,需要用sess.run(tf.local_variables_initializer())初始化
    # dataset_name = FLAGS.dataset_name
    # def get_dataset():
    #     outs = []
    #     for f in os.listdir(FLAGS.output_dir):
    #         if f.startswith(dataset_name):
    #             outs.append(os.path.join(FLAGS.output_dir, f))
    #     return outs

    dataset_name_files = "%s*" % os.path.join(FLAGS.output_dir, FLAGS.dataset_name)

    # outs = get_dataset()
    print("-------------------------")
    print(">>> outs: ")
    print(dataset_name_files)
    # print(outs)
    print("-------------------------")
    files = tf.train.match_filenames_once(dataset_name_files)
    filename_queue = tf.train.string_input_producer(files)

    reader = tf.TFRecordReader()
    _, serialized_example = reader.read(filename_queue)
    features = tf.parse_single_example(serialized_example, features={
        "image": tf.FixedLenFeature([], tf.string),
        'text': tf.FixedLenFeature([], tf.string),
        'width': tf.FixedLenFeature([], tf.int64),
        'height': tf.FixedLenFeature([], tf.int64),
        'channels': tf.FixedLenFeature([], tf.int64),
        'char_ids': tf.VarLenFeature(tf.int64)
    })

    # 设定的resize后的image的大小
    split_results = FLAGS.height_and_width.split(',')
    define_height = int(split_results[0].strip())
    define_width = int(split_results[1].strip())


    width, height, channels = features["width"], features["height"], features["channels"]
    img = tf.decode_raw(features["image"], tf.uint8)

    char_ids = tf.cast(features['char_ids'], tf.int32)
    img = tf.reshape(img, (define_height, define_width, 3))
    # img.set_shape([height, width, channels])

    text = tf.cast(features['text'], tf.string)

    myfont = fm.FontProperties(fname="fonts/card-id.TTF")
    # img, text, char_ids = read_tfrecord("datasets/training.tfrecords", 1, True)
    # img = preprocess_image(img, augment=True, num_towers=4)

    img = preprocess_train(img, augment=True)

    # img = vgg_preprocessing.preprocess_image(img, define_height, define_width, False)

    # img = inception_preprocessing.distort_color(img, random.randrange(0, 4), fast_mode=False, clip=False)
    img = tf.image.rgb_to_grayscale(img)
    img_batch, text_batch, ids_batch = tf.train.shuffle_batch([img, text, char_ids],
                                                              batch_size=8,
                                                              num_threads=1,
                                                              capacity=3000,
                                                              min_after_dequeue=1000)
    with tf.Session() as sess:

        init = (tf.global_variables_initializer(),
                tf.local_variables_initializer())
        sess.run(init)
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(coord=coord)
        try:
            # while not coord.should_stop():
            for x in range(5):
                imgs, texts, ids = sess.run([img_batch, text_batch, ids_batch])
                print("--------------")
                #print(ids_batch)
                #print(ids[2])
                #print(sess.run(tf.sparse_to_dense(ids_batch._indices, ids_batch._dense_shape, ids_batch._values)))
                print("--------------")
                #print(type(ids)) #tensorflow.python.framework.sparse_tensor.SparseTensorValue
                de_ids = decode_sparse_tensor(ids)
                print(imgs.shape)
                pos = random.randrange(0, imgs.shape[0])
                my_im = imgs[pos]  # random.choice(imgs)
                my_text = texts[pos]  # random.choice(texts)
                my_id = de_ids[pos]

                print("my_text:", decode_code(my_text))
                # print("my_ids:", de_ids)
                print("my_id:", my_id)
                print("my_id_str:", ''.join([chinese_dict_ids[code] for code in my_id]))

                plt.figure()
                plt.title("%s" % decode_code(my_text), fontproperties=myfont)
                # plt.imshow(my_im)
                plt.imshow(my_im[:,:,0], cmap ='gray')
                plt.show()
                # print(my_im.shape)
                # my_img = sess.run(img)
                # print(my_img.shape)
        except Exception as e:
            coord.request_stop(e)
        finally:
            coord.request_stop()
        coord.join(threads)


def write_dict():
    cs = open("resource/gb2312_list.txt", 'r').read()
    index = 134
    with open("resource/new_dic2.txt", 'a') as f:
        for c in cs:
            f.write("%d\t%c\n" % (index, c))
            index = index + 1


# python gen_record_crnn.py --dataset_name=train --dataset_dir=out --dataset_nums=10000 --output_dir=datasets/vgg_train
if __name__ == '__main__':
    chinese_dict = read_dict(FLAGS.dict_text)
    chinese_dict_ids = reverse_dict(chinese_dict)
    # print([chinese_dict[code] for code in "你好呀!"])
    # print([chinese_dict_ids[code] for code in [chinese_dict[code] for code in "你好呀!"]])
    # make_tfrecord2(chinese_dict, FLAGS.dataset_name, FLAGS.dataset_nums)

    # write_dict()
    # words = open("resource/gb2312_list.txt", 'r').read()
    # print(words)

    parse_tfrecord_file()





    #
    # import datasets

    # print(getattr(datasets, "my_data"))


    pass