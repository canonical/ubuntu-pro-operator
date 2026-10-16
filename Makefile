CLEANUP_FILES = charmcraft.yaml

.PHONY: ubuntu-pro ubuntu-pro_old ubuntu-advantage ubuntu-advantage_noble legacy clean

ubuntu-pro:
	cp charms/ubuntu-pro/* .
	charmcraft pack
	rm -f $(CLEANUP_FILES)

ubuntu-pro_old:
	cp charms/ubuntu-pro_old/* .
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
