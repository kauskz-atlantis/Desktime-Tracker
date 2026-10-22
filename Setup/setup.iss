#define AppExeName "ATL_Desk_Management_System.exe"

#define LoginApi ReadIni("config.ini", "Api", "Login")
#define RegistrationApi ReadIni("config.ini", "Api", "Registration")
#define UsernameApi ReadIni("config.ini", "Api", "Username")
#define Authorization ReadIni("config.ini", "Api", "Authorization")
#define XApiKey ReadIni("config.ini", "Api", "XApiKey")

[Setup]
AppName=ATL Desk Management System
AppVersion=3.2
AppPublisher=ATL
AppId={{A1B2C3D4-ATL-DESK-MANAGEMENT-2026}}

DefaultDirName=C:\ATLDeskManagement
DefaultGroupName=ATL Desk Management

OutputBaseFilename=ATL_Desk_Management_Setup
OutputDir=.

Compression=lzma2
SolidCompression=yes

PrivilegesRequired=admin
UsePreviousAppDir=yes
CloseApplications=yes
CloseApplicationsFilter= {#AppExeName}
RestartApplications=no
RestartIfNeededByRun=no

SetupIconFile=logo-a-dark.ico
UninstallDisplayIcon={app}\{#AppExeName}

WizardStyle=modern light
// WizardSizePercent=120

AlwaysShowDirOnReadyPage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes


[InstallDelete]
//Type: filesandordirs; Name: "{localappdata}\TrackerService"
//Type: files; Name: "{userstartup}\Tracker Service.lnk"
//Type: files; Name: "{localappdata}\TrackerService\tracker.exe"
Type: files; Name: "{app}\watchdog.exe"
//Type: files; Name: "{userstartup}\ATL Watchdog.lnk"
Type: files; Name: "{app}\ATLDeskManagementService.exe"
Type: files; Name: "{app}\ATLDeskManagementService.xml"

[Files]
Source: "dist\ATL_Desk_Management_System\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "kill_watchdog.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo-a-dark.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.bmp"; DestDir: "{tmp}"; Flags: dontcopy

[Dirs]
Name: "{commonappdata}\ATLDeskManagement"; Permissions: users-modify

[Icons]
Name: "{group}\ATL Desk Management"; Filename: "{app}\{#AppExeName}"

// RUNS AFTER INSTALLATION
[Run]
// LEGACY
Filename: "sc.exe"; Parameters: "stop ATLDeskManagement"; Flags: runhidden waituntilterminated
Filename: "sc.exe"; Parameters: "delete ATLDeskManagement"; Flags: runhidden waituntilterminated
Filename: "taskkill.exe"; Parameters: "/f /im ATLDeskManagementService.exe /t"; Flags: runhidden waituntilterminated
Filename: "taskkill.exe"; Parameters: "/f /im ATL_Desk_Management_System.exe /t"; Flags: runhidden waituntilterminated

Filename: "{cmd}"; Parameters: "/C del /F /Q ""{commonappdata}\ATLDeskManagement\tracker.log"""; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExeName}"; Flags: runhidden nowait

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ATLDeskManagement"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{commonappdata}\ATLDeskManagement"

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\kill_watchdog.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "KillWatchdog"
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#AppExeName} /t"; Flags: runhidden waituntilterminated; RunOnceId: "TaskKill"

[Code]
var
  WinHttpRequest: Variant;
  PostData: String;
  Serial: String;
  
  LoginPage: TWizardPage;
  
  LoginLogo: TBitmapImage;
  LoginTitle: TLabel;
  LoginSubtitle: TLabel;
  LoginLabelUsername: TLabel;
  LoginEditUsername: TEdit;
  LoginLabelPassword: TLabel;
  LoginEditPassword: TPasswordEdit;
  LoginCBShowPassword: TCheckBox;
  LoginLabelStatus: TLabel;
  
  DevicePage: TWizardPage;
  
  DeviceLogo: TBitmapImage;
  DeviceTitle: TLabel;
  DeviceSubtitle: TLabel;
  DeviceLabelUsername: TLabel;
  DeviceEditUsername: TEdit;
  DeviceLabelSerial: TLabel;
  DeviceEditSerial: TEdit;
  DeviceLabelEmp: TLabel;
  DeviceEditEmp: TEdit;

procedure HideDefaultControls;
begin
  WizardForm.WizardBitmapImage.Hide;
  WizardForm.WizardSmallBitmapImage.Hide;
  WizardForm.WelcomeLabel1.Hide;
  WizardForm.WelcomeLabel2.Hide;
end;

procedure ShowError(const ErrorText:String);
begin
  MsgBox(ErrorText, mbError, MB_OK);
end;

function VerifyCredentials(const UsernameText: String; const PasswordText: String): Boolean;
begin
  Result := False;
  
  if Trim(UsernameText) = '' then
  begin
    ShowError('Please enter username.');
    WizardForm.ActiveControl := LoginEditUsername;
    Exit;
  end
  else if Trim(PasswordText) = '' then
  begin
    ShowError('Please enter password.');
    WizardForm.ActiveControl := LoginEditPassword;
    Exit;
  end
  else
  begin
    try
      LoginLabelStatus.Caption := 'Authenticating...';
      WinHttpRequest := CreateOleObject('WinHttp.WinHttpRequest.5.1');
      WinHttpRequest.Open('POST', '{#LoginApi}', False);
      
      WinHttpRequest.SetRequestHeader('Authorization', '{#Authorization}');
      WinHttpRequest.SetRequestHeader('XApiKey', '{#XApiKey}');
      WinHttpRequest.SetRequestHeader('Content-Type', 'application/json');
      
      PostData :=
        '{' + 
        '"emp_id":"' + UsernameText + '",' +
        '"password":"' + PasswordText + '"' +
        '}';
      WinHttpRequest.Send(PostData);
      LoginLabelStatus.Caption := '';
      
      if WinHttpRequest.Status = 200 then
      begin
        if WinHttpRequest.ResponseText = '{"message":"Login Success"}' then
          Result := True
        else
          ShowError('Invalid username or password');
      end
      else
        ShowError('Could not connect to server');
    except
      ShowError('Error while sending request. Please try again.');
    end;
  end;
  
  LoginLabelStatus.Caption := '';
end;

procedure ShowPasswordClick(Sender: TObject);
begin
  LoginEditPassword.Password := not LoginCBShowPassword.Checked;
end;

function HandleRegistration(const Name:String; const Device:String; const Emp:String): Boolean;
begin
  Result := False;
  if Trim(Name) = '' then
  begin
    ShowError('Please enter user name.');
    WizardForm.ActiveControl := DeviceEditUsername;
    Exit;
  end
  else if Trim(Device) = '' then
  begin
    ShowError('Please enter device Serial Number.');
    WizardForm.ActiveControl := DeviceEditSerial;
    Exit;
  end
  else if Trim(Emp) = '' then
  begin
    ShowError('Please enter Employee ID.');
    WizardForm.ActiveControl := DeviceEditEmp;
    Exit;
  end
  else
  begin
    try
      WinHttpRequest := CreateOleObject('WinHttp.WinHttpRequest.5.1');
      WinHttpRequest.Open('POST', '{#RegistrationApi}', False);
      
      WinHttpRequest.SetRequestHeader('Authorization', '{#Authorization}');
      WinHttpRequest.SetRequestHeader('XApiKey', '{#XApiKey}');
      WinHttpRequest.SetRequestHeader('Content-Type', 'application/json');
      
      PostData :=
        '{' + 
        '"userName":"' + Name + '",' +
        '"SerialNumber":"' + Device + '",' +
        '"Emp_ID":"' + Emp + '"' +
        '}';
      WinHttpRequest.Send(PostData);
      
      if WinHttpRequest.Status = 200 then
      begin
        if WinHttpRequest.ResponseText = '{"success":true,"message":"Desk User Mapping Inserted Successfully"}' then
          Result := True
        else
          ShowError('Invalid username or password');
      end
      else
        ShowError('Could not connect to server');
    except
      ShowError('Error while sending request. Please try again.');
    end;
  end;
end;

function GetDeviceSerialNumber(): String;
var
  Locator: Variant;
  Services: Variant;
  BIOSInfo: Variant;
  BIOSList: Variant;
  SerialNumber: String;
begin
  Result := '';
  
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('.', 'root\cimv2');
    
    BIOSList := Services.ExecQuery('SELECT SerialNumber FROM Win32_BIOS');
    
    if BIOSList.Count > 0 then
    begin
      BIOSInfo := BIOSList.ItemIndex(0);
      SerialNumber := BIOSInfo.SerialNumber;
      Result := Trim(SerialNumber);
    end;
  except
    Result := '';
  end;
end;

function GetJsonStringValue(const Json:String; const Key:String) : String;
var
  KeyPos: Integer;
  ColonPos: Integer;
  StartPos: Integer;
  EndPos: Integer;
  I: Integer;
  Escaped: Boolean;
  SearchKey: String;
begin
  Result := '';
  
  SearchKey := '"' + Key + '"';
  
  KeyPos := Pos(SearchKey, Json);
  if KeyPos = 0 then
    Exit;
  
  ColonPos := KeyPos + Length(SearchKey);
  
  while (ColonPos <= Length(Json)) and (Json[ColonPos] in [' ', #9, #10, #13]) do
    Inc(ColonPos);
  
  if (ColonPos > Length(Json)) or (Json[ColonPos] <> ':') then
    Exit;
  
  Inc(ColonPos);
  
  while (ColonPos <= Length(Json)) and (Json[ColonPos] in [' ', #9, #10, #13]) do
    Inc(ColonPos);
  
  if (ColonPos > Length(Json)) or (Json[ColonPos] <> '"') then
    Exit;
  
  StartPos := ColonPos + 1;
  EndPos := StartPos;
  Escaped := False;
  
  while EndPos <= Length(Json) do
  begin
    if Escaped then
      Escaped := False
    else if Json[EndPos] = '\' then
      Escaped := True
    else if Json[EndPos] = '"' then
      Break;
    
    Inc(EndPos);
  end;
  
  if EndPos > Length(Json) then
    Exit;
  
  Result := Copy(Json, StartPos, EndPos - StartPos);
  
  I := 1;
  while I <= Length(Result) - 1 do
  begin
    if Result[I] = '\' then
    begin
      if Result[I + 1] in ['"', '\', '/'] then
        Result := Copy(Result, 1, I - 1) + Result[I + 1] + Copy(Result, I + 2, Length(Result));
    end;
    
    Inc(I);
  end;
end;

function GetUserNameFromSerial(const SerialNumber:String) : String;
begin
  Result := '';
  try
    WinHttpRequest := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    WinHttpRequest.Open('GET', '{#UsernameApi}', False);
    WinHttpRequest.SetRequestHeader('Authorization', '{#Authorization}');
    WinHttpRequest.SetRequestHeader('XApiKey', '{#XApiKey}');
    WinHttpRequest.SetRequestHeader('Content-Type', 'application/json');
    
    PostData := '{"SerialNumber":"' + SerialNumber + '"}';
    WinHttpRequest.Send(PostData);
    
    if WinHttpRequest.Status = 200 then
    begin
      Result := GetJsonStringValue(WinHttpRequest.ResponseText, 'Emp_ID');
    end
    else
      Result := '';
  except
    Result := '';
  end;
end;

procedure InitializeWizard;
begin;
  WizardForm.Width := ScaleX(900);
  WizardForm.Height := ScaleY(600);
  WizardForm.Color := clWhite;
   
  HideDefaultControls();

  LoginPage := CreateCustomPage(wpWelcome, '', '')
  
  LoginLogo := TBitmapImage.Create(LoginPage);
  LoginLogo.Parent := LoginPage.Surface;
  ExtractTemporaryFile('logo.bmp');
  LoginLogo.Bitmap.LoadFromFile(ExpandConstant('{tmp}\logo.bmp'));
  LoginLogo.Stretch := True;
  LoginLogo.Width := 240;
  LoginLogo.Height := 180;
  LoginLogo.Left := 20;
  LoginLogo.Top := (LoginPage.Surface.Height - LoginLogo.Height) div 2;
  
  LoginTitle := TLabel.Create(LoginPage);
  LoginTitle.Parent := LoginPage.Surface;
  LoginTitle.Caption := 'Welcome';
  LoginTitle.Font.Size := 24;
  LoginTitle.Font.Style := [fsBold];
  LoginTitle.Left := LoginLogo.Left + LoginLogo.Width + 80;
  LoginTitle.Top := 20;
  
  LoginSubtitle := TLabel.Create(LoginPage);
  LoginSubtitle.Parent := LoginPage.Surface;
  LoginSubtitle.Caption := 'Sign in to continue ATL Tracker installation.';
  LoginSubtitle.Font.Size := 12;
  LoginSubtitle.Top := LoginTitle.Top + LoginTitle.Height + 10;
  LoginSubtitle.Left := LoginTitle.Left;
  
  LoginLabelUsername := TLabel.Create(LoginPage);
  LoginLabelUsername.Parent := LoginPage.Surface;
  LoginLabelUsername.Caption := 'Username';
  LoginLabelUsername.Left := LoginSubtitle.Left;
  LoginLabelUsername.Top := LoginSubtitle.Top + LoginSubtitle.Height + 40;
  LoginLabelUsername.Font.Style := [fsBold];
  
  LoginEditUsername := TEdit.Create(LoginPage);
  LoginEditUsername.Parent := LoginPage.Surface;
  LoginEditUsername.Left := LoginLabelUsername.Left;
  LoginEditUsername.Top := LoginLabelUsername.Top + LoginLabelUsername.Height + 12;
  LoginEditUsername.Width := 240;
  
  LoginLabelPassword := TLabel.Create(LoginPage);
  LoginLabelPassword.Parent := LoginPage.Surface;
  LoginLabelPassword.Caption := 'Password';
  LoginLabelPassword.Left := LoginEditUsername.Left;
  LoginLabelPassword.Top := LoginEditUsername.Top + LoginEditUsername.Height + 20;
  LoginLabelPassword.Font.Style := [fsBold];
  
  LoginEditPassword := TPasswordEdit.Create(LoginPage);
  LoginEditPassword.Parent := LoginPage.Surface;
  LoginEditPassword.Left := LoginLabelPassword.Left;
  LoginEditPassword.Top := LoginLabelPassword.Top + LoginLabelPassword.Height + 12;
  LoginEditPassword.Width := 240;
  
  LoginCBShowPassword := TCheckBox.Create(LoginPage);
  LoginCBShowPassword.Parent := LoginPage.Surface;
  LoginCBShowPassword.Caption := 'Show password';
  LoginCBShowPassword.Left := LoginEditPassword.Left;
  LoginCBShowPassword.Top := LoginEditPassword.Top + LoginEditPassword.Height + 10;
  LoginCBShowPassword.Width := 200;
  LoginCBShowPassword.Checked := False;
  LoginCBShowPassword.OnClick := @ShowPasswordClick;
  
  LoginLabelStatus := TLabel.Create(LoginPage);
  LoginLabelStatus.Parent := LoginPage.Surface;
  LoginLabelStatus.Left := LoginCBShowPassword.Left;
  LoginLabelStatus.Top := LoginCBShowPassword.Top + LoginCBShowPassword.Height + 20;
  LoginLabelStatus.Font.Color := clRed;
  LoginLabelStatus.Caption := '';
  
  
  DevicePage := CreateCustomPage(LoginPage.ID, '', '');
  
  DeviceLogo := TBitmapImage.Create(DevicePage);
  DeviceLogo.Parent := DevicePage.Surface;
  ExtractTemporaryFile('logo.bmp');
  DeviceLogo.Bitmap.LoadFromFile(ExpandConstant('{tmp}\logo.bmp'));
  DeviceLogo.Stretch := True;
  DeviceLogo.Width := 240;
  DeviceLogo.Height := 180;
  DeviceLogo.Left := 20;
  DeviceLogo.Top := (DevicePage.Surface.Height - DeviceLogo.Height) div 2;
  
  DeviceTitle := TLabel.Create(DevicePage);
  DeviceTitle.Parent := DevicePage.Surface;
  DeviceTitle.Caption := 'Device Registration';
  DeviceTitle.Font.Size := 24;
  DeviceTitle.Font.Style := [fsBold];
  DeviceTitle.Left := DeviceLogo.Left + DeviceLogo.Width + 80;
  DeviceTitle.Top := 20;
  
  DeviceSubtitle := TLabel.Create(DevicePage);
  DeviceSubtitle.Parent := DevicePage.Surface;
  DeviceSubtitle.Caption := 'Register local device details';
  DeviceSubtitle.Font.Size := 12;
  DeviceSubtitle.Top := DeviceTitle.Top + DeviceTitle.Height + 10;
  DeviceSubtitle.Left := DeviceTitle.Left;
  
  DeviceLabelUsername := TLabel.Create(DevicePage);
  DeviceLabelUsername.Parent := DevicePage.Surface;
  DeviceLabelUsername.Caption := 'User Name';
  DeviceLabelUsername.Left := DeviceSubtitle.Left;
  DeviceLabelUsername.Top := DeviceSubtitle.Top + DeviceSubtitle.Height + 40;
  DeviceLabelUsername.Font.Style := [fsBold];
  
  DeviceEditUsername := TEdit.Create(DevicePage);
  DeviceEditUsername.Parent := DevicePage.Surface;
  DeviceEditUsername.Left := DeviceLabelUsername.Left;
  DeviceEditUsername.Top := DeviceLabelUsername.Top + DeviceLabelUsername.Height + 12;
  DeviceEditUsername.Width := 240;

  DeviceLabelSerial := TLabel.Create(DevicePage);
  DeviceLabelSerial.Parent := DevicePage.Surface;
  DeviceLabelSerial.Caption := 'Serial Number';
  DeviceLabelSerial.Left := DeviceEditUsername.Left;
  DeviceLabelSerial.Top := DeviceEditUsername.Top + DeviceEditUsername.Height + 40;
  DeviceLabelSerial.Font.Style := [fsBold];
  
  DeviceEditSerial := TEdit.Create(DevicePage);
  DeviceEditSerial.Parent := DevicePage.Surface;
  DeviceEditSerial.Left := DeviceLabelSerial.Left;
  DeviceEditSerial.Top := DeviceLabelSerial.Top + DeviceLabelSerial.Height + 12;
  DeviceEditSerial.Width := 240;

  DeviceLabelEmp := TLabel.Create(DevicePage);
  DeviceLabelEmp.Parent := DevicePage.Surface;
  DeviceLabelEmp.Caption := 'Employee ID';
  DeviceLabelEmp.Left := DeviceEditSerial.Left;
  DeviceLabelEmp.Top := DeviceEditSerial.Top + DeviceEditSerial.Height + 40;
  DeviceLabelEmp.Font.Style := [fsBold];
  
  DeviceEditEmp := TEdit.Create(DevicePage);
  DeviceEditEmp.Parent := DevicePage.Surface;
  DeviceEditEmp.Left := DeviceLabelEmp.Left;
  DeviceEditEmp.Top := DeviceLabelEmp.Top + DeviceLabelEmp.Height + 12;
  DeviceEditEmp.Width := 240;
  
  Serial := GetDeviceSerialNumber();
  DeviceEditSerial.Text := Serial;
  DeviceEditEmp.Text := GetUserNameFromSerial(Serial);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = LoginPage.ID then
    WizardForm.NextButton.Caption := 'Sign In'
  else if CurPageID = DevicePage.ID then
    WizardForm.NextButton.Caption := 'Register';
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine + NewLine;
  Result := Result + WizardForm.DiskSpaceLabel.Caption + NewLine;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin;
  if (CurPageID = LoginPage.ID) then
    Result := VerifyCredentials(LoginEditUsername.Text, LoginEditPassword.Text)
  else if CurPageID = DevicePage.ID then
    Result := HandleRegistration(DeviceEditUsername.Text, DeviceEditSerial.Text, DeviceEditEmp.Text)
  else
    Result := True;
end;

function InitializeUninstall: Boolean;
var
  ResultCode: Integer;
 begin
  Result := False;
  if Exec('cmd.exe', '/v:on /c "set /p pass=Enter password to uninstall: && if !pass!==YourSecurePassword123 (exit 0) else (exit 1)"', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then Result := True
    else
    begin
      MsgBox('Incorrect password! Uninstallation cancelled.', mbError, MB_OK);
      Result := False;
    end;
  end
  else
    Result := False;
end;