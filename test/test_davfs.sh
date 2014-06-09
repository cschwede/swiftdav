MOUNTPOINT="/mnt/webdav"
DIRNAME=`echo -n 'test_swiftdav_davfs_' ; cat /dev/urandom | tr -cd 'a-f0-9' | head -c 8`
DIRNAME2=`echo -n 'test_swiftdav_davfs_' ; cat /dev/urandom | tr -cd 'a-f0-9' | head -c 8`
FILENAME=`echo -n 'test_swiftdav_davfs_' ; cat /dev/urandom | tr -cd 'a-f0-9' | head -c 8`
FILENAME2=`echo -n 'test_swiftdav_davfs_' ; cat /dev/urandom | tr -cd 'a-f0-9' | head -c 8`
echo "" > $FILENAME

mkdir $MOUNTPOINT/$DIRNAME
mkdir $MOUNTPOINT/$DIRNAME2

# Create new file
echo "" > $MOUNTPOINT/$DIRNAME/$FILENAME
cmp $FILENAME $MOUNTPOINT/$DIRNAME/$FILENAME

# Modify existing file
echo "data" > $FILENAME
echo "data" > $MOUNTPOINT/$DIRNAME/$FILENAME
cmp $FILENAME $MOUNTPOINT/$DIRNAME/$FILENAME

# Rename file
mv $MOUNTPOINT/$DIRNAME/$FILENAME $MOUNTPOINT/$DIRNAME/$FILENAME2
cmp $FILENAME $MOUNTPOINT/$DIRNAME/$FILENAME2

# Move file to other container
mv $MOUNTPOINT/$DIRNAME/$FILENAME2 $MOUNTPOINT/$DIRNAME2/$FILENAME2
cmp $FILENAME $MOUNTPOINT/$DIRNAME2/$FILENAME2

# Remove everything
rm $FILENAME
rm $MOUNTPOINT/$DIRNAME2/$FILENAME2
rmdir $MOUNTPOINT/$DIRNAME
rmdir $MOUNTPOINT/$DIRNAME2

# Verify containers are deleted
[[ ! -e "$MOUNTPOINT/$DIRNAME" ]] || echo "$MOUNTPOINT/$DIRNAME exists"
[[ ! -e "$MOUNTPOINT/$DIRNAME2" ]] || echo "$MOUNTPOINT/$DIRNAME2 exists"
