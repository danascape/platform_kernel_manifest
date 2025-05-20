# Kernel Build Guide

## Supported Devices

| Device       | Repository Branch    | Kernel Version | Commit-ID                                      | Binary Path                  |
| ------------ | -------------------- | -------------- | ---------------------------------------------- | ---------------------------- |
| Asus Max M1  | android-msm-x00p-3.18 | 3.18.140       | 993f59db42c97629bc0346fdc69df52f13a17b3d      | device/asus/X00P-kernel      |

---

## Getting Started

Follow the steps below to get started with building the kernel for the supported devices.

### 1. Initialize the Repository

First, you need to initialize the repo and sync the required branches. Run the following commands to initialize and sync the repository:

```bash
repo init -u https://github.com/danascape/platform_kernel_manifest -b $MANIFEST_BRANCH
repo sync -j8
```

### 2. Build the Kernel

After syncing the repository, you can proceed with the kernel build process. To build the kernel, follow these steps:

```bash
build/build.sh
```
