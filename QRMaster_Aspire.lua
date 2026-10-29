-- VECTRIC LUA SCRIPT
-- QRMaster Aspire 1.1.0 / square pocket vectors.
local script_dir = ''
local TITLE = 'QRМастер Aspire 1.1.0'
local RELEASES = 'https://github.com/i-strannik-i/QRMaster-Aspire/releases/latest'

local function run(values,quiet)
  local request=os.tmpname()
  local output=request..'.lua'
  local f,err=io.open(request,'w')
  if not f then
    if not quiet then MessageBox('Не удалось записать параметры: '..tostring(err)) end
    return nil
  end
  for key,value in pairs(values) do
    if tostring(value):find('[\r\n]') then
      f:close();os.remove(request)
      if not quiet then MessageBox('Уберите переносы строк из поля '..key) end
      return nil
    end
    f:write(key,'=',tostring(value),'\n')
  end
  f:close()
  local exe=script_dir..'\\__runtime\\QRMasterEngine.exe'
  os.execute('""'..exe..'" "'..request..'" "'..output..'""')
  local loader=loadfile(output)
  os.remove(request)
  if not loader then
    os.remove(output)
    if not quiet then MessageBox('QRMasterEngine.exe не запустился. Переустановите гаджет.') end
    return nil
  end
  local success,result=pcall(loader)
  os.remove(output)
  if not success or not result.ok then
    if not quiet then MessageBox(success and result.message or tostring(result)) end
    return nil
  end
  return result
end

local function create_vectors(url,cutter)
  local job=VectricJob()
  if not job.Exists then MessageBox('Сначала создайте или откройте проект Aspire.');return false end
  local result=run({url=url,cutter=cutter},false)
  if not result then return false end
  local scale=job.InMM and 1 or 1/25.4
  if result.size*scale>job.Width+0.000001 or result.size*scale>job.Height+0.000001 then
    MessageBox(string.format('QR %.2f × %.2f мм с защитным полем не помещается на лист. Увеличьте лист или уменьшите фрезу.',result.size,result.size));return false
  end
  local function point(x,y) return Point2D(job.MinX+x*scale,job.MinY+y*scale) end
  local pending={}
  for _,points in ipairs(result.contours) do
    local contour=Contour(0)
    contour:AppendPoint(point(points[1][1],points[1][2]))
    for i=2,#points do contour:LineTo(point(points[i][1],points[i][2])) end
    pending[#pending+1]=CreateCadContour(contour)
  end
  local layer=job.LayerManager:GetLayerWithName('QR_SQUARES')
  layer.Colour=0
  job.Selection:Clear()
  for _,object in ipairs(pending) do
    layer:AddObject(object,true)
    job.Selection:Add(object,true,false)
  end
  job:Refresh2DView()
  Registry('QRMasterAspire_1'):SetString('cutter',cutter)
  return true
end

function OnLuaButton_OpenUpdate(dialog)
  os.execute('start "" "'..RELEASES..'"')
  return true
end

function main(path)
  script_dir=path
  if not VectricJob().Exists then MessageBox('Сначала создайте или откройте проект Aspire.');return false end
  local update=run({task='update_check'},true)
  local update_text=update and update.message or 'Проверка обновлений недоступна. Генератор работает без интернета.'
  if update and update.available then MessageBox(update.message..' Кнопка «Обновить» откроет новый релиз.') end
  local url=''
  local cutter=Registry('QRMasterAspire_1'):GetString('cutter','4')
  while true do
    local dialog=HTML_Dialog(false,'file:'..path..'\\QRMaster_Aspire.html',600,440,TITLE)
    dialog:AddTextField('url',url)
    dialog:AddTextField('cutter',cutter)
    dialog:AddLabelField('update_status',update_text)
    dialog:AddLabelField('update_available',update and update.available and '1' or '0')
    if not dialog:ShowDialog() then return true end
    url=dialog:GetTextField('url');cutter=dialog:GetTextField('cutter')
    if create_vectors(url,cutter) then return true end
  end
end
