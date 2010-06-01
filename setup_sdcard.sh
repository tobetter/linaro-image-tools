#!/bin/bash -e

# Copyright 2010, Canonical Ltd.
# License: GPLv3 
# Based on rcn's setup_sdcard.sh script.
# Notes: need to check for: parted, fdisk, wget, mkfs.*, mkimage, md5sum

set -e

MLO_FILE="MLO.omap"
UBOOT_FILE="u-boot.bin.omap"

unset MMC MMC1 MMC2 MMC3

#Defaults
RFS=ext3
BOOT_LABEL=boot
RFS_LABEL=rootfs
CODENAME=Chessy
RFS_UUID=`uuidgen -r`
IS_LIVE=

DIR=$PWD

function get_mmcs_by_id {
  for device in /dev/disk/by-id/*; do
    if [ `realpath $device` = $MMC ]; then
      if echo $device | grep -q -- "-part[0-9]*$"; then
        echo "device $MMC must not be a partition part ($device)" 1>&2
	exit 1
      fi
      for part_id in `ls $device-part*`; do
        part=`realpath $part_id`
	part_no=`echo $part_id | sed -e 's/.*-part//g'`
        # echo "part $part_no found: $part_id" 1>&2
        if test "$part_no" = 1; then
          MMC1=$part
        elif test "$part_no" = 2; then
          MMC2=$part
        elif test "$part_no" = 3; then
          MMC3=$part
        fi
      done
      break
    fi
  done
}

function prepare_sources {
 if [ "$CHESSY_SOURCE" ] ; then

  if [ "$IS_LIVE" ]; then
    parts_dir=casper
    boot_snippet='boot=casper'
    [ "$IS_LOWMEM" ] && lowmem_opt=only-ubiquity
  else
    parts_dir=boot
    boot_snippet='root=UUID='${RFS_UUID}
  fi

  rm -rf ${DIR}/${parts_dir}/ || true
  rm -rf initrd.img-* || true
  rm -rf vmlinuz-* || true
  tar xf binary-boot.omap.tar.gz 
  ln -sf ${parts_dir}/initrd.img-* .
  ln -sf ${parts_dir}/vmlinuz-* .

  cat > boot.cmd << BOOTCMD
setenv bootcmd 'mmc init; fatload mmc 0:1 0x80000000 uImage; fatload mmc 0:1 0x81600000 uInitrd; bootm 0x80000000 0x81600000'
setenv bootargs '${serial_opts} ${splash_opts} earlyprintk fixrtc nocompcache ${lowmem_opt} ${boot_snippet} rootwait ro vram=12M omapfb.debug=y omapfb.mode=dvi:1280x720MR-16@60'
boot
BOOTCMD
 fi
}

function cleanup_sd {

 echo ""
 echo "Umounting Partitions"
 echo ""

 if test -n "$MMC1"; then
   sudo umount ${MMC1} &> /dev/null || true
 fi
 if test -n "$MMC2"; then
   sudo umount ${MMC2} &> /dev/null || true
 fi

 sudo parted -s ${MMC} mklabel msdos
}

function create_partitions {

sudo fdisk -H 255 -S 63 ${MMC} << END
n
p
1
1
+64M
a
1
t
e


n
p
2


p
w
END

}

function prepare_partitions {

echo ""
echo "Formating Boot Partition"
echo ""

sudo mkfs.vfat -F 16 ${MMC1} -n ${BOOT_LABEL}

echo ""
echo "Formating ${RFS} Partition"
echo ""
sudo mkfs.${RFS} -U "$RFS_UUID" ${MMC2} -L ${RFS_LABEL}
}

function populate_boot {
 echo ""
 echo "Populating Boot Partition"
 echo ""

 echo ""
 echo "Installing OMAP Boot Loader"
 echo ""

 if [ "$IS_LIVE" ]; then
   parts_dir=casper
 else
   parts_dir=boot
 fi

 mkdir -p ${DIR}/disk || true
 sudo mount ${MMC1} ${DIR}/disk
 if test -e ${parts_dir}/${MLO_FILE} -a -e ${parts_dir}/${UBOOT_FILE}; then
   sudo cp -v ${parts_dir}/${MLO_FILE} ${DIR}/disk/MLO
   sudo cp -v ${parts_dir}/${UBOOT_FILE} ${DIR}/disk/u-boot.bin
 fi
 sync
 cd ${DIR}
 echo "done"

 sudo cp -f ${DIR}/${parts_dir}/uImage.omap ${DIR}/disk/uImage
 sudo cp -f ${DIR}/${parts_dir}/uInitrd.omap ${DIR}/disk/uInitrd

 sudo mkimage -A arm -O linux -T script -C none -a 0 -e 0 -n "$CODENAME 10.05" -d ${DIR}/boot.cmd ${DIR}/disk/boot.scr
 sudo cp -v ${DIR}/disk/boot.scr ${DIR}/disk/boot.ini

 echo "#!/bin/sh" > /tmp/rebuild_uinitrd.sh
 echo "" >> /tmp/rebuild_uinitrd.sh
 echo "DIR=\$PWD" >> /tmp/rebuild_uinitrd.sh
 echo "sudo mkimage -A arm -O linux -T ramdisk -C none -a 0 -e 0 -n initramfs -d /boot/initrd.img-\$(uname -r) \${DIR}/uInitrd" >> /tmp/rebuild_uinitrd.sh
 echo "" >> /tmp/rebuild_uinitrd.sh

 sudo cp -v /tmp/rebuild_uinitrd.sh ${DIR}/disk/rebuild_uinitrd.sh
 sudo chmod +x ${DIR}/disk/rebuild_uinitrd.sh

 cd ${DIR}/disk/
 sync
 sync
 cd ${DIR}/

 sudo umount ${DIR}/disk || true
}

function populate_rootfs {
 echo ""
 echo "Populating rootfs Partition"
 echo "Be patient, this may take a few minutes"
 echo ""
 sudo mount ${MMC2} ${DIR}/disk

 if [ "$CHESSY_SOURCE" ] ; then
  sudo tar xfp binary-tar.tar.lzma --lzma --strip-components=1 -C disk/ 2>/dev/null || sudo tar xzfp binary-tar.tar.gz  --strip-components=1 -C disk/
 else
  sudo tar xfp ${DIR}/armel-rootfs-* -C ${DIR}/disk/
 fi

 if [ "$CREATE_SWAP" ] ; then

  echo ""
  echo "Creating SWAP File"
  echo ""

  SPACE_LEFT=$(df ${DIR}/disk/ | grep ${MMC2} | awk '{print $4}')

  let SIZE=$SWAP_SIZE*1024

  if [ $SPACE_LEFT -ge $SIZE ] ; then
   sudo dd if=/dev/zero of=${DIR}/disk/mnt/SWAP.swap bs=1M count=$SWAP_SIZE
   sudo mkswap ${DIR}/disk/mnt/SWAP.swap
   echo "/mnt/SWAP.swap  none  swap  sw  0 0" | sudo tee -a ${DIR}/disk/etc/fstab
   else
   echo "FIXME Recovery after user selects SWAP file bigger then whats left not implemented"
  fi
 fi

 cd ${DIR}/disk/
 sync
 sync
 cd ${DIR}/

 sudo umount ${DIR}/disk || true
}

function check_mmc {
 DISK_NAME="Disk|Platte"
 FDISK=$(sudo fdisk -l | grep "[${DISK_NAME}] ${MMC}" | awk '{print $2}')

 if test "-$FDISK-" = "-$MMC:-"
 then
  echo ""
  echo "I see..."
  echo "sudo fdisk -l:"
  sudo fdisk -l | grep "[${DISK_NAME}] /dev/" --color=never
  echo ""
  echo "mount:"
  mount | grep -v none | grep "/dev/" --color=never
  echo ""
  read -p "Are you 100% sure, on selecting [${MMC}] (y/n)? "
  [ "$REPLY" == "y" ] || exit
  echo ""
 else
  echo ""
  echo "Are you sure? I Don't see [${MMC}], here is what I do see..."
  echo ""
  echo "sudo fdisk -l:"
  sudo fdisk -l | grep "[${DISK_NAME}] /dev/" --color=never
  echo ""
  echo "mount:"
  mount | grep -v none | grep "/dev/" --color=never
  echo ""
  exit
 fi
}

function check_fs_type {
 IN_VALID_FS=1

 if test "-$FS_TYPE-" = "-ext2-"
 then
 RFS=ext2
 unset IN_VALID_FS
 fi

 if test "-$FS_TYPE-" = "-ext3-"
 then
 RFS=ext3
 unset IN_VALID_FS
 fi

 if test "-$FS_TYPE-" = "-ext4-"
 then
 RFS=ext4
 unset IN_VALID_FS
 fi

 if test "-$FS_TYPE-" = "-btrfs-"
 then
 RFS=btrfs
 unset IN_VALID_FS
 fi

 if [ "$IN_VALID_FS" ] ; then
   usage
 fi
}

function usage {
    echo "usage: $(basename $0) --mmc /dev/sdd"
cat <<EOF

required options:
--mmc </dev/sdX>
    Unformated MMC Card

Additional/Optional options:
-h --help
    this help

--rootfs <fs_type>
    ext2
    ext3 - <set as default>
    ext4
    btrfs

--boot_label <boot_label>
    boot partition label

--rfs_label <rfs_label>
    rootfs partition label

--swap_file <xxx>
    Creats a Swap file of (xxx)MB's

--live
    Create boot command for casper/live images; if this is not
    provided a UUID for the rootfs is generated and used as the root=
    option

--live-256m
    Create boot command for casper/live images; adds only-ubiquity option
    to allow use of live installer on boards with 256M memory - like beagle

--dev <board>
    use development boot options; this includes setting up serial ttys as well
    as enabling normal debug options for the target board. Current board values:
    * beagle

--console <ttyXY>
    add a console to kernel boot parameter; this parameter can be defined
    multiple times.

EOF
exit
}

function checkparm {
    if [ "$(echo $1|grep ^'\-')" ];then
        echo "E: Need an argument"
        usage
    fi
}

consoles=""

# parse commandline options
while [ ! -z "$1" ]; do
    case $1 in
        -h|--help)
            usage
            MMC=1
            ;;
        --mmc)
            checkparm $2
            MMC="$2"
            check_mmc 
            ;;
        --rootfs)
            checkparm $2
            FS_TYPE="$2"
            check_fs_type 
            ;;
        --boot_label)
            checkparm $2
            BOOT_LABEL="$2"
            ;;
        --rfs_label)
            checkparm $2
            RFS_LABEL="$2"
            ;;
        --swap_file)
            checkparm $2
            SWAP_SIZE="$2"
            CREATE_SWAP=1
            ;;
        --live)
            IS_LIVE=1
            ;;
        --live-256m)
            IS_LIVE=1
            IS_LOWMEM=1
            ;;
        --console)
            checkparm $2
            consoles="$consoles $2"
            ;;
        --chessy)
            CHESSY_SOURCE=1
            ;;
	--dev)
            checkparm $2
            DEVIMAGE=$2
            ;;
    esac
    shift
done

serial_opts=""
if [ "$consoles" ]; then
  for c in ${consoles}; do 
    serial_opts="$serial_opts console=$c"
  done
  if [ "$IS_LIVE" ]; then 
    serial_opts="$serial_opts serialtty=ttyS2"
  fi
fi

if [ "$DEVIMAGE" ]; then
  case "$DEVIMAGE" in
    beagle)
      serial_opts="$serial_opts console=tty0 console=ttyS2,115200n8"
      if [ "$IS_LIVE" ]; then
        serial_opts="$serial_opts serialtty=ttyS2"
      fi
      ;;
    *)
      echo "unknown --dev paramater: $DEVIMAGE" 1>&2
      ;;
  esac
else
  if [ "$IS_LIVE" ]; then
    splash_opts="quiet splash"
  fi
fi

if [ ! "${MMC}" ];then
    usage
fi

 prepare_sources
 get_mmcs_by_id
 cleanup_sd
 create_partitions
 echo -n "waiting for partitioning to settle ..."
 sync
 sleep 3
 echo "done."
 get_mmcs_by_id
 if test -z "$MMC1" -o -z "$MMC2"; then
   echo "MMC1: $MMC1 nor MMC2: $MMC2 must be empty"
   exit 2
 fi
 prepare_partitions
 populate_boot
 populate_rootfs

