Title: Holiday readings (New Year 2025): AI accelerators and GPU clouds
Date: 2025-01-10 16:45
Tags: readings, AI accelerators, GPU clouds, LLMs
Summary: Just before Christmas, I've stumbled upon [Machine Learning Engineering Open Book](https://github.com/stas00/ml-engineering) by Stas Bekman. It's a book I've long been looking for – a collection of insights on operating a large GPU cluster and using it to train and run LLMs: AI accelerators, fast intra-node and inter-node networking, optimized cluster storage, large-scale LLM training and inference, with lots of first-hand experience on these topics. I want to share my key takes from the book as well as other excellent resources I've discovered in the process.

Just before Christmas, I've stumbled upon [Machine Learning Engineering Open Book](https://github.com/stas00/ml-engineering) by Stas Bekman. It's a book I've long been looking for – a collection of insights on operating a large GPU cluster and using it to train and run LLMs: AI accelerators, fast intra-node and inter-node networking, optimized cluster storage, large-scale LLM training and inference, with lots of first-hand experience on these topics. I want to share my key takes from the book as well as other excellent resources I've discovered in the process.

## AI accelerators

With the rise of LLMs, the market of AI accelerators began growing quickly. There are lots of options available: Nvidia GPUs, AMD GPUs, Google TPUs, AWS Trainium, Intel Gaudi, Cerebras, and many others. Yet, Nvidia totally dominates the market with a [~85% market share](https://finance.yahoo.com/news/nvidia-dominates-ai-chips-analyst-143411443.html). Google TPUs account for the majority of the remaining 15% but they are mostly used internally by Google. All other chips combined take a few percent of the market share. Why is that?

I had an impression that Nvidia dominance is due to historical reasons ([first-mover advantage](https://en.wikipedia.org/wiki/First-mover_advantage)) and also their excellent software: CUDA, NCCL, etc. This being true, I also learned that Nvidia has another key advantage: networking.

In LLM training, [intra-node and inter-node GPU networking](https://github.com/stas00/ml-engineering/tree/master/network#intra-node-networking) (GPUs inside the node vs. GPUs between the nodes) is so important that it often determines the performance of a GPU cluster. Nvidia offers custom networking solutions: NVLink/NVSwitch for intra-node networking and InfiniBand for inter-node networking. NVLink Switch is yet another technology that essentially makes inter-node networking as fast as intra-node. While competitors try to match Nvidia solutions on paper, this is a big advantage in practice.

So it seems that Nvidia will continue to dominate in training. With inference, the situation is a bit different. While networking is also important when you do inference of a model split across many GPUs and nodes, the memory bandwidth is often the bottleneck.

**Note on memory bandwidth**: GPUs have large High Bandwidth Memory (HBM). For example, H100 has 80GB. Some LLMs can fit into HBM entirely. But GPUs perform computations using registers/cache that can only store megabytes of data. So the model weights need to be moved constantly from HBM when doing a forward pass. The speed of doing that is determined by the GPU memory bandwidth. If the batch size is small (i.e. few inputs are processed in parallel), the GPU performs less operations with the loaded weights than it can, and thus GPU compute that you pay for is underutilized. This becomes less of a problem when you do inference with large batch sizes, but that can be tricky. In training, using large batch sizes is typical.

Nvidia does not have a significant advantage in memory capacity and bandwidth. For example, Nvidia latest H200 has 141GB HBM with 4800GB/s bandwidth, and AMD MI300X has 192GB with 5300GB/s. Moreover, new accelerator architectures like Cerebrus have different trade-offs that can be more suitable for inference. My prediction is that Nvidia should be expecting significant competition in the inference space.

## GPU clouds

My another Christmas discovery is [SemiAnalysis](https://semianalysis.com). It's a group of expert researches that analyze AI accelerators, AI clouds, data centers, and semiconductors markets, and write excellent articles about it. I particularly liked reading [AI Neocloud Playbook and Anatomy](https://semianalysis.com/2024/10/03/ai-neocloud-playbook-and-anatomy/). They describe in great detail how to build a GPU cluster: buying and setting up the hardware, configuring networking, monitoring, with insights into day-to-day operations. Overall, SemiAnalysis posts gave me a lot of though about GPU clouds market.

It was quite a surprise for me that besides hyperscalers (AWS, Azure, GCP, OCI, and several Chinese providers), SemiAnalysis tracks more than 80 Neoclouds (that many!). The main four Neoclouds are Crusoe, Nebius, Lambda Labs, and Coreweave, which is [by far the largest](https://news.crunchbase.com/ai/coreweave-raises-7-5b-in-debt-for-ai-push/). SemiAnalysis predicts that even though the market will grow, the number of Neoclouds is going to decrease as many fail to differentiate themselves. 

How do GPU clouds differ from each other? They all say they offer H100 clusters or similar, but H100 clusters can be very different in terms of performance and UX. We've already talked about networking, which is one aspect:

> Most Neoclouds’ target customers are not interested in having anything less than 8x400Gbit/s InfiniBand bandwidth per compute server. Because it does impact workload performance. This is one of the primary reasons why many firms are allergic to Google Cloud. Google Cloud deploys H100s with 8x200Gbit/s Ethernet using Falcon/GRD. – [semianalysis.com](https://semianalysis.com/2024/10/03/ai-neocloud-playbook-and-anatomy/)

Another aspect is storage. GPU cluster users want a fast shared storage. This typically means having `/home/$USER/` and `/data/` directories mounted for reads and writes on all nodes of the cluster. This can't be achieved with network storage on a regular file system like ext4. You need to set up a [distributed parallel file system](https://en.wikipedia.org/wiki/Comparison_of_distributed_file_systems) like Lustre FS, GPFS, and GlusterFS. It's not easy to operate. So some GPU clouds offer fast and reliable storage out-of-the-box, while others don't.

**Side note**: I'm still early on this but I'm looking deep into shared storage solutions from big clouds like [AWS FSx for Lustre](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html) and [GCP Filestore](https://cloud.google.com/filestore). Big clouds have several offerings for shared network storage (e.g. AWS has EFS and AWS FSx for Lustre) and I want to better understand the pros and cons of each for different ML workloads. This is a part of my work on [dstack](https://github.com/dstackai/dstack) – there are plans to provide performant shared storage in different clouds that can be provisioned and used via the same interface.

There many other factors affecting the UX of a GPU cluster: the presence of managed orchestrator like Slurm or Kubernetes, the hardware reliability, monitoring tools, etc. I'm still unsure what conclusions to draw from that about GPU clouds market, but it's exciting and I'm going to follow it closely.

## Bonus by Hugging Face

Hugging Face has long had an [NLP course](https://huggingface.co/learn/nlp-course/chapter1/1) that focuses on using the `transformers` library and Hugging Face ecosystem to run and train transformer models. It's introductory but I found immense value going through it to better understand what the `transformers` library does exactly when you call `pipeline()`, `tokenizer()`, etc.

The bonus is that Hugging Face has just published a [course on aligning models](https://github.com/huggingface/smol-course) (SFT, RHLF, DPO, and such). I'm yet to enroll but it looks promising for someone who only read about the alignment techniques.

<br>

*If you have any questions, comments or suggestions, feel free to join the [GitHub discussion](https://github.com/r4victor/tenthousandmeters/discussions/2).*
