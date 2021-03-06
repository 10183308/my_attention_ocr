import os,re,logging,random
import codecs
import json
import glob
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import  matplotlib.font_manager as fm
import tensorflow as tf
from multiprocessing import Pool
import time
import tqdm

import inception_preprocessing
from data_provider import preprocess_image

from utils import preprocess_train

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
                           'datasets/train',
                           'where to save the generated tfrecord file')

tf.app.flags.DEFINE_bool('test',
                           False,
                           'The test tf recored')

tf.app.flags.DEFINE_integer('thread',
                           10,
                           'the thread count')


tf.app.flags.DEFINE_string('suffix', 'png', 'suffix of image in data set')
tf.app.flags.DEFINE_string('height_and_width', '32, 320', 'input size of each image in model training')
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



def get_image_files(image_dir,check=False):
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
                #cv2.imread(fp)
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


def make_tfrecord(dict_chinese, dataset_name, nums):
    """
    制作 tfrecord 文件
    :return:
    """
    if not os.path.exists(FLAGS.output_dir):
        os.makedirs(FLAGS.output_dir)

    image_tupe = get_image_files(FLAGS.dataset_dir)

    average_samples = len(image_tupe) // nums
    print('count:{} images in dir:{}, nums:{}, avg:{}'.format(len(image_tupe), FLAGS.dataset_dir, nums, average_samples))

    # 图片resize的高和宽
    split_results = FLAGS.height_and_width.split(',')
    height = int(split_results[0].strip())
    width = int(split_results[1].strip())


    def get_tfrecord_writer(start, end):
        filename = os.path.join(FLAGS.output_dir, dataset_name + '.tfrecords-%.5d-of-%.5d' %(start, end))
        tfrecord_writer = tf.python_io.TFRecordWriter(filename)
        print('{} / {}, {}'.format(start, end, filename))
        return tfrecord_writer
    start = 0
    def get_end(start):
        end = (start + nums)
        if len(image_tupe) - start < nums:
            end = len(image_tupe)
        return end
    tfrecord_writer = get_tfrecord_writer(start, get_end(start))
    for path_img, label in image_tupe:
        img = Image.open(path_img)
        orig_width = img.size[0]
        orig_height = img.size[1]
        img = img.resize((width, height), Image.ANTIALIAS)
        image_data = img.tobytes()

        char_ids_padded, char_ids_unpadded = encode_utf8_string(text=label, length=FLAGS.length_of_text,
                                                                dic=dict_chinese, null_char_id=FLAGS.null_char_id)
        one_sample = tf.train.Example(features=tf.train.Features(
            feature={
                'image/encoded': _bytes_feature(image_data),
                'image/format': _bytes_feature(b'raw'),
                # 'image/format': _bytes_feature(b"png"),
                'image/width': _int64_feature([width]),
                'image/orig_width': _int64_feature([orig_width]),
                'image/class': _int64_feature(char_ids_padded),
                'image/unpadded_class': _int64_feature(char_ids_unpadded),
                'image/text': _bytes_feature(bytes(label, 'utf-8'))
            }
        ))
        tfrecord_writer.write(one_sample.SerializeToString())
        start += 1
        if start%nums == 0:
            tfrecord_writer.close()
            end = (start+nums)
            if len(image_tupe) - start < nums:
                end = len(image_tupe)
            tfrecord_writer = get_tfrecord_writer(start, end)
    tfrecord_writer.close()
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
        #print('{} / {}, {}'.format(start, end, filename))
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
    #print(image_tupe)
    #print("start:%d-of-end:%d" % (start, end))

    # 图片resize的高和宽
    split_results = FLAGS.height_and_width.split(',')
    height = int(split_results[0].strip())
    width = int(split_results[1].strip())

    tfrecord_writer = tf.python_io.TFRecordWriter(filename)

    for path_img, label in image_tupe:
        img = Image.open(path_img)
        orig_width = img.size[0]
        orig_height = img.size[1]
        if (orig_width != width) and (orig_height != height):
            img = img.resize((width, height), Image.ANTIALIAS)
        image_data = img.tobytes()

        char_ids_padded, char_ids_unpadded = encode_utf8_string(text=label, length=FLAGS.length_of_text,
                                                                dic=dict_chinese, null_char_id=FLAGS.null_char_id)
        one_sample = tf.train.Example(features=tf.train.Features(
            feature={
                'image/encoded': _bytes_feature(image_data),
                'image/format': _bytes_feature(b'raw'),
                # 'image/format': _bytes_feature(b"png"),
                'image/width': _int64_feature([width]),
                'image/orig_width': _int64_feature([orig_width]),
                'image/class': _int64_feature(char_ids_padded),
                'image/unpadded_class': _int64_feature(char_ids_unpadded),
                'image/text': _bytes_feature(bytes(label, 'utf-8'))
            }
        ))
        tfrecord_writer.write(one_sample.SerializeToString())
    tfrecord_writer.close()
    return filename
def parse_tfrecord_file():
    reader = tf.TFRecordReader()
    # 创建一个队列来维护输入文件列表
    # filename_queue = tf.train.string_input_producer([FLAGS.path_save_tfrecord])
    # 注，files 是一个local variable，不会保存到checkpoint,需要用sess.run(tf.local_variables_initializer())初始化
    # dataset_name = FLAGS.dataset_name
    # def get_dataset():
    #     outs = []
    #     for f in os.listdir(FLAGS.output_dir):
    #         if f.startswith(dataset_name):
    #             outs.append(os.path.join(FLAGS.output_dir, f))
    #     return outs

    dataset_name_files = "%s*"%os.path.join(FLAGS.output_dir, FLAGS.dataset_name)

    # outs = get_dataset()
    print("-------------------------")
    print(">>> outs: ")
    print(dataset_name_files)
    # print(outs)
    print("-------------------------")
    files = tf.train.match_filenames_once(dataset_name_files)
    filename_queue = tf.train.string_input_producer(files)
    # 读取一个样列
    _, serialized_example = reader.read(filename_queue)
    # 解析样列
    features = tf.parse_single_example(serialized_example, features={
        'image/encoded': tf.FixedLenFeature([], tf.string),
        'image/format': tf.FixedLenFeature([], tf.string),
        'image/width': tf.FixedLenFeature([], tf.int64),
        'image/orig_width': tf.FixedLenFeature([], tf.int64),
        'image/class': tf.FixedLenFeature([FLAGS.length_of_text], tf.int64),
        'image/unpadded_class': tf.VarLenFeature(tf.int64),
        'image/text': tf.FixedLenFeature([], tf.string)
    })

    # 设定的resize后的image的大小
    split_results = FLAGS.height_and_width.split(',')
    define_height = int(split_results[0].strip())
    define_width = int(split_results[1].strip())

    img = tf.decode_raw(features['image/encoded'], tf.uint8)
    img = tf.reshape(img, (define_height, define_width, 3))
    width = tf.cast(features['image/width'], tf.int32)
    ori_width = tf.cast(features['image/orig_width'], tf.int32)
    img_class = tf.cast(features['image/class'], tf.int32)
    img_unpaded_class = tf.cast(features['image/unpadded_class'], tf.int32)
    text = tf.cast(features['image/text'], tf.string)

    myfont = fm.FontProperties(fname="fonts/card-id.TTF")

    #
    # img = inception_preprocessing.distort_color(img, random.randrange(0, 4), fast_mode=False, clip=False)
    # img = preprocess_image(img, augment=True, num_towers=4)

    img = preprocess_train(img, augment=True)
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        sess.run(tf.local_variables_initializer())

        # 启动多线程处理输入数据
        # Starts all queue runners collected in the graph
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess, coord)
        print(sess.run(files))
        for i in range(10):
            # 每次运行会自动读取tfrecord文件中的一个样列，当所有样列读取完后，会重头读取
            one_image, one_width, one_ori_width, one_img_class, one_img_unpaded_class,one_text = sess.run(
                [img, width, ori_width, img_class, img_unpaded_class, text])
            # 可视化解析出来的图片
            # one_image = np.reshape(one_image, (define_height, define_width, 3))
            print("text:", decode_code(one_text))
            plt.figure()
            plt.title("%s"%decode_code(one_text),fontproperties=myfont)
            plt.imshow(one_image)
            plt.show()
        #关闭
        coord.request_stop()
        coord.join(threads)

def write_dict():
    cs = open("resource/gb2312_list.txt", 'r').read()
    index = 134
    with open("resource/new_dic2.txt", 'a') as f:
        for c in cs:
            f.write("%d\t%c\n" % (index, c))
            index = index+1



#python gen_record.py --dataset_name=train --dataset_dir=out --dataset_nums=1024 --output_dir=datasets/train
if __name__ == '__main__':
    chinese_dict = read_dict(FLAGS.dict_text)
    # make_tfrecord2(chinese_dict, FLAGS.dataset_name, FLAGS.dataset_nums)


    # write_dict()
    # words = open("resource/gb2312_list.txt", 'r').read()
    # print(words)

    parse_tfrecord_file()
    #
    # import datasets

    # print(getattr(datasets, "my_data"))


    pass