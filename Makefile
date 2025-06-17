CLEANUP_FILES = charmcraft.yaml

.PHONY: all ubuntu-advantage ubuntu-advantage_noble ubuntu-pro ubuntu-pro_noble clean

all: ubuntu-advantage ubuntu-advantage_noble ubuntu-pro ubuntu-pro_noble

ubuntu-advantage:
	cp charms/ubuntu-advantage/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)
	
ubuntu-advantage_noble:
	cp charms/ubuntu-advantage_noble/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

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
