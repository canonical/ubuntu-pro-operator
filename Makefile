CLEANUP_FILES = charmcraft.yaml

.PHONY: all ubuntu-pro ubuntu-pro_noble legacy clean

all: ubuntu-pro ubuntu-pro_noble

ubuntu-pro:
	cp charms/ubuntu-pro/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)
	
ubuntu-pro_noble:
	cp charms/ubuntu-pro_noble/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

ubuntu-advantage:
	cp charms/ubuntu-advantage/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

ubuntu-advantage_noble:
	cp charms/ubuntu-advantage_noble/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

legacy:
	make ubuntu-advantage ubuntu-advantage_noble

clean:
	rm -f $(CLEANUP_FILES)
	
