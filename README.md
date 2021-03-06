## Attention-based Extraction of Structured Information from Street View Imagery

*A TensorFlow model for real-world image text extraction problems.*

源代码[tensorflow models](https://github.com/tensorflow/models/blob/master/research/attention_ocr)

Attention OCR model 使用 [FSNS dataset][FSNS] 数据训练的模型。
你也可以使用自己的数据集

论文详情:

["Attention-based Extraction of Structured Information from Street View
Imagery"](https://arxiv.org/abs/1704.03549)

## Contacts

原作者:

Zbigniew Wojna <zbigniewwojna@gmail.com>,
Alexander Gorban <gorban@google.com>

Pull requests:
[alexgorban](https://github.com/alexgorban)

## Requirements

1. 安装环境脚本:

```
install_env.sh
```

2. 生成自己的数据:

```
python gen_run.py -t 15 -fs 28 -new_h 32 -new_w 320 -w 2 -c 200000 -news -mxw 18 -miw 15 -l cn -e png -aug  --output_dir out
```

3. 生成训练数据格式：
```
python gen_record.py --dataset_name=train --dataset_dir=out --dataset_nums=10000 --output_dir=datasets/train
```

4. 修改训练配置在:
```
 my_data.py
```

5. 训练:
```
 train.py --dataset_name=my_data
```

6. Inception下载地址:

```
wget http://download.tensorflow.org/models/inception_resnet_v2_2016_08_30.tar.gz
wget http://download.tensorflow.org/models/inception_v4_2016_09_09.tar.gz
wget http://download.tensorflow.org/models/inception_v3_2016_08_28.tar.gz
tar xf inception_v3_2016_08_28.tar.gz
mv inception_v3.ckpt resource/inception_v3.ckpt
```
#### .1. 使用Inception_v3权重训练:
```
 python train.py --checkpoint_inception=./resource/inception_v3.ckpt --dataset_name=my_data > output.log 2>&1 &
```

6. 使用Attention OCR model权重训练:

```
wget http://download.tensorflow.org/models/attention_ocr_2017_08_09.tar.gz
tar xf attention_ocr_2017_08_09.tar.gz
python train.py --checkpoint=../attention_ocr_2017_08_09/model.ckpt-399731 --train_log_dir=my_logs --dataset_name=my_data
```

7. 可视化:

```
tensorboard  --logdir=logs
```


8. 验证：
```
python eval.py --dataset_name=my_data --split_name=test

tensorboard  --logdir=eval_logs --port=6016
```


### train.sh 有完整的训练步骤
