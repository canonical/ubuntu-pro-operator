CLEANUP_FILES = charmcraft.yaml

.PHONY: all ubuntu-pro ubuntu-pro_noble clean

all: ubuntu-pro ubuntu-pro_noble

ubuntu-pro:
	cp charms/ubuntu-pro/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)
	
ubuntu-pro_noble:
	cp charms/ubuntu-pro_noble/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

clean:
	rm -f $(CLEANUP_FILES)
