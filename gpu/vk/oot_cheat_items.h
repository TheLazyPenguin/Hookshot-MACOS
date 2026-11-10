/* (OoT debug cheats) the inventory editor's items, shared by the menu (gpu/vk/vk_menu.cpp) and the game side
   (host/hos_main.c). OOT_SECTION starts a heading in the menu list; OOT_ITEM(label, pouch content name, kind):
   kind 0 an item Link has or not (Enter unlocks / relocks), 1 a quantity (Left / Right change it).
   Pouch names come from the game's own event flows and actor packs (work/oot-teleport-research.md, "Inventory").
   The names marked (guess) are the likeliest of two spellings; the log's "inventory probe" line shows both. */
#ifndef OOT_CHEAT_ITEMS
#define OOT_CHEAT_ITEMS(OOT_SECTION, OOT_ITEM) \
    OOT_SECTION("Equipment") \
    OOT_ITEM("Kokiri Sword", "Weapon_Sword_Kokiri", 0) \
    OOT_ITEM("Master Sword", "Weapon_Sword_Master", 0) \
    OOT_ITEM("Giant's Knife", "Weapon_Sword_Giant", 0) \
    OOT_ITEM("Biggoron's Sword", "Weapon_Sword_Biggoron", 0) \
    OOT_ITEM("Deku Shield", "Weapon_Shield_Deku", 0) \
    OOT_ITEM("Hylian Shield", "Weapon_Shield_Hylian", 0) \
    OOT_ITEM("Mirror Shield", "Weapon_Shield_Mirror", 0) \
    OOT_ITEM("Goron Tunic", "Armor_Adult_Goron", 0) \
    OOT_ITEM("Zora Tunic", "Armor_Adult_Zora", 0) \
    OOT_ITEM("Iron Boots", "Armor_Adult_HeavyBoot", 0) \
    OOT_ITEM("Hover Boots", "Armor_Adult_HoverBoot", 0) \
    OOT_SECTION("Items") \
    OOT_ITEM("Deku Sticks", "Item_DekuStick", 1) \
    OOT_ITEM("Deku Nuts", "Item_DekuNut", 1) \
    OOT_ITEM("Bombs", "Item_Bomb", 1) \
    OOT_ITEM("Bombchus", "Item_Bombchu", 1) \
    OOT_ITEM("Fairy Slingshot", "Weapon_Range_SlingShot", 0) \
    OOT_ITEM("Deku Seeds", "Item_DekuSeed", 1) \
    OOT_ITEM("Fairy Bow", "Weapon_Range_Bow", 0) \
    OOT_ITEM("Arrows", "Item_Arrow_Normal", 1) \
    OOT_ITEM("Fire Arrow", "Item_Arrow_Fire", 0) \
    OOT_ITEM("Ice Arrow", "Item_Arrow_Ice", 0) \
    OOT_ITEM("Light Arrow", "Item_Arrow_Light", 0) \
    OOT_ITEM("Din's Fire", "Item_DinFire", 0) \
    OOT_ITEM("Farore's Wind", "Item_FaroreWind", 0) \
    OOT_ITEM("Nayru's Love", "Item_NayruLove", 0) \
    OOT_ITEM("Fairy Ocarina", "Item_Ocarina_Fairy", 0) \
    OOT_ITEM("Ocarina of Time", "Item_Ocarina_Time", 0) \
    OOT_ITEM("Hookshot", "Item_Hookshot", 0) \
    OOT_ITEM("Longshot", "Item_Longshot", 0) \
    OOT_ITEM("Boomerang", "Item_Boomerang", 0) \
    OOT_ITEM("Lens of Truth", "Item_GlassTruth", 0) \
    OOT_ITEM("Magic Beans", "Item_MagicBean", 1) \
    OOT_ITEM("Megaton Hammer", "Item_Hammer", 0) \
    OOT_ITEM("Empty Bottle", "Item_Bottle", 1) \
    OOT_SECTION("Masks") \
    OOT_ITEM("Keaton Mask", "Armor_Child_Mask_Keaton", 0) \
    OOT_ITEM("Skull Mask", "Armor_Child_Mask_Skull", 0) \
    OOT_ITEM("Spooky Mask", "Armor_Child_Mask_Spooky", 0) \
    OOT_ITEM("Bunny Hood", "Armor_Child_Mask_Bunny", 0) \
    OOT_ITEM("Goron Mask", "Armor_Child_Mask_Goron", 0) \
    OOT_ITEM("Zora Mask", "Armor_Child_Mask_Zora", 0) \
    OOT_ITEM("Gerudo Mask", "Armor_Child_Mask_Gerudo", 0) \
    OOT_ITEM("Mask of Truth", "Armor_Child_Mask_Truth", 0) \
    OOT_SECTION("Upgrades") \
    OOT_ITEM("Goron's Bracelet", "Item_Gauntlet_Goron", 0) \
    OOT_ITEM("Silver Gauntlets", "Armor_Adult_Gauntlet_Silver", 0) \
    OOT_ITEM("Golden Gauntlets", "Armor_Adult_Gauntlet_Gold", 0) \
    OOT_ITEM("Silver Scale", "Item_Scale_Silver", 0) \
    OOT_ITEM("Golden Scale", "Item_Scale_Gold", 0) \
    OOT_ITEM("Bomb Bag", "Item_BombBag_Small", 0) \
    OOT_ITEM("Big Bomb Bag", "Item_BombBag_Medium", 0) \
    OOT_ITEM("Biggest Bomb Bag", "Item_BombBag_Large", 0) \
    OOT_ITEM("Quiver", "Item_Quiver_Small", 0) \
    OOT_ITEM("Big Quiver", "Item_Quiver_Medium", 0) \
    OOT_ITEM("Biggest Quiver", "Item_Quiver_Large", 0) \
    OOT_ITEM("Bullet Bag", "Item_BulletBag_Small", 0) \
    OOT_ITEM("Big Bullet Bag", "Item_BulletBag_Medium", 0) \
    OOT_ITEM("Biggest Bullet Bag", "Item_BulletBag_Large", 0) \
    OOT_ITEM("Adult's Wallet", "Item_Wallet_Medium", 0) \
    OOT_ITEM("Giant's Wallet", "Item_Wallet_Large", 0) \
    OOT_ITEM("Magic Meter", "Item_FairyBless_MP", 0) \
    OOT_ITEM("Double Magic", "Item_FairyBless_MPDouble", 0) \
    OOT_ITEM("Double Defense", "Item_FairyBless_DefenseDouble", 0) \
    OOT_SECTION("Quest") \
    OOT_ITEM("Kokiri's Emerald", "Item_Stone_Forest", 0) \
    OOT_ITEM("Goron's Ruby", "Item_Stone_Fire", 0) \
    OOT_ITEM("Zora's Sapphire", "Item_Stone_Water", 0) \
    OOT_ITEM("Forest Medallion", "Item_Medal_Forest", 0) \
    OOT_ITEM("Fire Medallion", "Item_Medal_Fire", 0) \
    OOT_ITEM("Water Medallion", "Item_Medal_Water", 0) \
    OOT_ITEM("Shadow Medallion", "Item_Medal_Shadow", 0) \
    OOT_ITEM("Spirit Medallion", "Item_Medal_Spirit", 0) \
    OOT_ITEM("Light Medallion", "Item_Medal_Light", 0) \
    OOT_ITEM("Zelda's Lullaby", "Item_Melody_ZeldaLullaby", 0) \
    OOT_ITEM("Epona's Song", "Item_Melody_EponaSong", 0) \
    OOT_ITEM("Saria's Song", "Item_Melody_SariaSong", 0) \
    OOT_ITEM("Sun's Song", "Item_Melody_SunSong", 0) \
    OOT_ITEM("Song of Time", "Item_Melody_TimeSong", 0) \
    OOT_ITEM("Song of Storms", "Item_Melody_StormSong", 0) \
    OOT_ITEM("Minuet of Forest", "Item_Melody_ForestMinuet", 0) \
    OOT_ITEM("Bolero of Fire", "Item_Melody_FireBolero", 0) \
    OOT_ITEM("Serenade of Water", "Item_Melody_WaterSerenade", 0) \
    OOT_ITEM("Nocturne of Shadow", "Item_Melody_ShadowNocturne", 0) \
    OOT_ITEM("Requiem of Spirit", "Item_Melody_SpiritRequiem", 0) \
    OOT_ITEM("Prelude of Light", "Item_Melody_LightPrelude", 0) \
    OOT_ITEM("Stone of Agony", "Item_AgonyStone", 0) \
    OOT_ITEM("Gerudo's Card", "Item_Token_Gerudo", 0) \
    OOT_ITEM("Gold Skulltula Tokens", "Item_Token_Gold", 1)
#endif

/* (other spellings the game might use for the same item: logged once by the game side for checking) */
#define OOT_CHEAT_ITEM_PROBES \
    "Item_Sword_Kokiri", "Item_Sword_Giant", "Item_Sword_Biggoron", "Item_Shield_Mirror", "Item_Range_Bow", \
    "Item_Range_SlingShot", "Weapon_Range_Hookshot", "Weapon_Range_Longshot", "Weapon_Boomerang", "Weapon_Hammer", \
    "Item_HeavyBoot", "Item_HoverBoot", "Item_Mask_Keaton", "Item_Gauntlet_Silver", "Armor_GlassTruth", "Armor_Child_GlassTruth", "Armor_Adult_GlassTruth", \
    "Armor_Child_Gauntlet_Goron", "Item_Wallet_Small"

#define OOT_CHEAT_ITEM_BASE 4096   /* rx_option_set(OOT_CHEAT_ITEM_BASE + i, count) from the game side; -1 unknown */
#define OOT_CHEAT_AGE_ID 4090      /* rx_option_set(OOT_CHEAT_AGE_ID, age) from the game side: 0 child, 1 adult, -1 unknown */
#define OOT_CHEAT_ITEM_ACTION 3000 /* + item * 256 + op: op 0..127 adds op - 64; op 200 unlocks (1) or relocks (all) */
