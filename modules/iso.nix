{ lib, ... }:

{
  image.baseName = lib.mkForce "synapseos";
  isoImage.squashfsCompression = "zstd -Xcompression-level 6";
  boot.supportedFilesystems.zfs = lib.mkForce false;

  # Live image only: the user has no password, and sudo needs none.
  users.users.synapse.initialHashedPassword = lib.mkForce "";
  services.getty.autologinUser = lib.mkForce "synapse";

  synapseos.aiTools.enable = true;
  synapseos.dashboard.enable = true;
}
