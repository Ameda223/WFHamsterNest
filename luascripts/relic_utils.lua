--[[
	数据来源于英文维基
	-> https://wiki.warframe.com/w/Module:Void/data
]]

--[[
  规则说明:
  * 入库(relic vaulted): 遗物无法从游戏任务获得。
  * 物品入库: 该物品所有部件可掉落的所有遗物均已入库。
  * 例外: Frost & Ember Prime Vault (Lith G1/Meso F2/Neo S5/Axi E1)、
          Nyx & Rhino Prime Vault (Lith B4/Meso N6/Neo R1/Axi S3)、
          Baro 系列 (Neo O1/Axi A2/Axi A5/Axi M5/Axi V8)

  Ducat 定价(默认):
  * Rare      -> 100
  * Uncommon  -> 45
  * Common    -> 15
  * Common + Rare       -> 25
  * Common + Uncommon   -> 25
  * Uncommon + Rare     -> 65

  关系模型:
  Relic 1---* Drop *---1 Part *---1 Item
  (一个 Relic 掉落多个 Part; 一个 Part 由多个 Relic 掉落; 一个 Part 只属于一个 Item)
]]

local RelicData = require("luascripts/relic_data")

-- ============================================================
-- 类型定义
-- ============================================================

---@alias Rarity "Common" | "Uncommon" | "Rare"

---@alias LotusColor
---| "gcrmid"  # 金+铜（含 Common+Rare）
---| "scrmid"  # 银+铜（含 Common+Uncommon）
---| "gsrmid"  # 金+银（含 Uncommon+Rare）
---| "silver"  # 纯 Uncommon
---| "copper"  # 纯 Common
---| "gold"    # 纯 Rare
---| "default"

---@class PartData
---@field Drops table<string, Rarity>  # relicName -> rarity
---@field DucatValue number
---@field LotusColor LotusColor

---@class ItemData
---@field Parts table<string, PartData>
---@field IsVaulted boolean

---@alias PrimeData table<string, ItemData>

-- ============================================================
-- 常量
-- ============================================================

--- 由于稀有度分布导致杜卡德价格例外的情况
---@type table<string, table<string, number>>
local DUCAT_EXCEPTIONS = {
  Forma                     = { Blueprint = 0 },
  ["Khora Prime"]           = { Blueprint = 65 },
  ["Akstiletto Prime"]      = { Receiver = 45 },
  ["Knell Prime"]           = { Receiver = 45 },
  ["Braton Prime"]          = { Receiver = 45 },
  ["Rubico Prime"]          = { Stock = 45 },
  ["Saryn Prime"]           = { ["Neuroptics Blueprint"] = 45 },
  ["Soma Prime"]            = { Blueprint = 15 },
  ["Mesa Prime"]            = { ["Systems Blueprint"] = 100 },
  ["Gauss Prime"]           = { Blueprint = 25 },
  ["Panthera Prime"]        = { Receiver = 100 },
  ["Fang Prime"]            = { Blueprint = 15 },
  ["Limbo Prime"]           = { ["Neuroptics Blueprint"] = 100 },
  ["Exilus Weapon Adapter"] = { Blueprint = 0 },
  ["Riven Sliver"]          = { [""] = 0 },
  ["Kuva"]                  = { [""] = 0 },
  ["Ayatan Amber Star"]     = { [""] = 0 },
  ["Xata"]                  = { [""] = 0 },
  ["Lohk"]                  = { [""] = 0 },
  ["Vome"]                  = { [""] = 0 },
  ["Jahu"]                  = { [""] = 0 },
  ["Fass"]                  = { [""] = 0 },
  ["Ris"]                   = { [""] = 0 },
  ["Netra"]                 = { [""] = 0 },
  ["Khra"]                  = { [""] = 0 },
  -- 新增遇到的
  ["Reaper Prime"]          = { Blueprint = 15 },
  -- 先锋中的银部件, 以后应该 65
  ["Caliban Prime"]         = { ["Neuroptics Blueprint"] = 100 },
  ["Sevagoth Prime"]        = { ["Blueprint"] = 45 },
  ["Bronco Prime"]          = { Barrel = 25 }, -- 10.15已经改为25了
}

-- ============================================================
-- 内部工具函数
-- ============================================================

--- 返回某物品部件在所有遗物中的稀有度集合
---@param primeData PrimeData
---@param itemName string
---@param partName string
---@return table<Rarity, true>
local function getItemRarities(primeData, itemName, partName)
  local part = primeData[itemName].Parts[partName]
  local rarityDict = {}

  for _, rarity in pairs(part.Drops) do
    rarityDict[rarity] = true
  end

  if next(rarityDict) == nil then
    error(('getItemRarities: no drop rarities found for "%s" part "%s"')
      :format(itemName, partName))
  end

  return rarityDict
end

--- 根据稀有度组合返回杜卡德价值
---@param itemName string
---@param partName string
---@param rarities table<Rarity, true>
---@return number
local function computeDucatValue(itemName, partName, rarities)
  local exceptions = DUCAT_EXCEPTIONS[itemName]
  if exceptions ~= nil and exceptions[partName] ~= nil then
    return exceptions[partName]
  end

  local hasCommon   = rarities.Common
  local hasUncommon = rarities.Uncommon
  local hasRare     = rarities.Rare

  -- 双稀有度组合（优先级与原实现一致）
  if hasCommon and hasUncommon then return 25 end
  if hasUncommon and hasRare then return 65 end

  -- 单一稀有度
  if hasRare then return 100 end
  if hasUncommon then return 45 end
  if hasCommon then return 15 end

  error(('computeDucatValue: "%s" part "%s" has unsupported rarities')
    :format(itemName, partName))
end

--- 根据稀有度组合返回 Lotus 颜色标记
---@param rarities table<Rarity, true>
---@return LotusColor
local function computeLotusColor(rarities)
  local hasCommon   = rarities.Common
  local hasUncommon = rarities.Uncommon
  local hasRare     = rarities.Rare

  if hasCommon and hasRare then return "gcrmid" end     -- 金+铜
  if hasCommon and hasUncommon then return "scrmid" end -- 银+铜
  if hasUncommon and hasRare then return "gsrmid" end   -- 金+银
  if hasUncommon then return "silver" end
  if hasCommon then return "copper" end
  if hasRare then return "gold" end
  return "default"
end

--- 判断某物品是否已入库（其所有部件的所有遗物均已入库）
---@param itemTable ItemData
---@return boolean
local function isItemVaulted(itemTable)
  for _, partTable in pairs(itemTable.Parts) do
    for relicName in pairs(partTable.Drops) do
      local relic = RelicData[relicName]
      -- 只要找到任意一个未入库的遗物，此物品即未入库
      if relic ~= nil and relic.Vaulted == nil then
        return false
      end
    end
  end
  return true
end

-- ============================================================
-- PrimeData 构建
-- ============================================================

---@type PrimeData
local PrimeData = (function()
  ---@type PrimeData
  local primeData = {}

  -- 遍历所有遗物, 建立 Item -> Part -> Relics 索引
  for relicName, relicEntry in pairs(RelicData) do
    for _, drop in pairs(relicEntry.Drops) do
      local itemName = drop.Item
      local partName = drop.Part

      local item = primeData[itemName]
      if item == nil then
        ---@type ItemData
        item = { Parts = {}, IsVaulted = false }
        primeData[itemName] = item
      end

      local part = item.Parts[partName]
      if part == nil then
        ---@type PartData
        part = { Drops = {}, DucatValue = 0, LotusColor = "default" }
        item.Parts[partName] = part
      end

      part.Drops[relicName] = drop.Rarity
    end
  end

  -- 一次性计算 IsVaulted / DucatValue / LotusColor
  for itemName, itemTable in pairs(primeData) do
    itemTable.IsVaulted = isItemVaulted(itemTable)
    for partName, partTable in pairs(itemTable.Parts) do
      local rarities       = getItemRarities(primeData, itemName, partName)
      partTable.DucatValue = computeDucatValue(itemName, partName, rarities)
      partTable.LotusColor = computeLotusColor(rarities)
    end
  end

  return primeData
end)()

-- ============================================================
-- 对外接口
-- ============================================================

--- 获取某个 Prime 部件的杜卡德金币价值
---@param itemName string
---@param partName string
---@return number|nil
local function GetDucatValue(itemName, partName)
  local item = PrimeData[itemName]
  if item == nil then return nil end

  local part = item.Parts[partName]
  if part == nil then return nil end

  return part.DucatValue
end

--- 获取 Lotus 颜色标记（用于 UI 显示）
---@param itemName string
---@param partName string
---@return LotusColor
local function GetLotusColor(itemName, partName)
  local item = PrimeData[itemName]
  if item == nil then return "default" end

  local part = item.Parts[partName]
  if part == nil then return "default" end

  return part.LotusColor
end

--- 判断某个 Prime 物品是否已入库
---@param itemName string
---@return boolean
local function IsPrimeVaulted(itemName)
  local data = PrimeData[itemName]
  return data ~= nil and data.IsVaulted
end

--- 获取部件掉落于哪些遗物
---@param itemName string
---@param partName string
---@return table
local function GetRelicNames(itemName, partName)
  local item = PrimeData[itemName]
  if item == nil then return {} end

  local part = item.Parts[partName]
  if part == nil then return {} end

  local n = {}
  for relicName, _ in pairs(part.Drops) do
    table.insert(n, relicName)
  end

  return n
end

return {
  GetDucatValue   = GetDucatValue,
  GetLotusColor   = GetLotusColor,
  IsPrimeVaulted  = IsPrimeVaulted,
  GetRelicNames   = GetRelicNames,
}
