# API Client Endpoint Summary

## AccountsClient
- Base path: `/accounts`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listAccountsAccountsGet` | GET | `/accounts` | — | `AccountList[]` |
| `createAccountsAccountsPost` | POST | `/accounts` | `AccountCreate` | `AccountGet` |
| `deleteAccountsAccountsIdDelete` | DELETE | `/accounts/{id}` | — | `void` |
| `getAccountsAccountsIdGet` | GET | `/accounts/{id}` | — | `AccountGet` |
| `updateAccountsAccountsIdPatch` | PATCH | `/accounts/{id}` | `AccountUpdate` | `AccountGet` |

## AuthenticationClient
- Base path: `/auth`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listAllPluginsAuthAdminPluginsGet` | GET | `/auth/admin/plugins` | — | `Record<string, unknown> & Record<string, unknown>` |
| `reloadPluginsAuthAdminPluginsReloadPost` | POST | `/auth/admin/plugins/reload` | — | `Record<string, unknown> & Record<string, unknown>` |
| `disablePluginAuthAdminPluginsPluginNameDisablePost` | POST | `/auth/admin/plugins/{plugin_name}/disable` | — | `Record<string, unknown> & Record<string, unknown>` |
| `enablePluginAuthAdminPluginsPluginNameEnablePost` | POST | `/auth/admin/plugins/{plugin_name}/enable` | — | `Record<string, unknown> & Record<string, unknown>` |
| `loginWithCredentialsAuthLoginPost` | POST | `/auth/login` | `LocalLoginRequest` | `LocalLoginResponse` |
| `logoutAuthLogoutPost` | POST | `/auth/logout` | — | `LogoutResponse` |
| `listProvidersAuthProvidersGet` | GET | `/auth/providers` | — | `ProviderInfo[]` |
| `refreshTokenAuthRefreshPost` | POST | `/auth/refresh` | `TokenRefreshRequest` | `TokenRefreshResponse` |
| `refreshLocalTokenAuthRefreshLocalPost` | POST | `/auth/refresh/local` | `LocalTokenRefreshRequest` | `LocalTokenRefreshResponse` |
| `registerUserAuthRegisterPost` | POST | `/auth/register` | `UserRegistrationRequest` | `UserRegistrationResponse` |
| `ssoSuccessAuthSuccessGet` | GET | `/auth/success` | — | `void` |
| `handleCallbackAuthProviderCallbackGet` | GET | `/auth/{provider}/callback` | — | `void` |
| `initiateLoginAuthProviderLoginGet` | GET | `/auth/{provider}/login` | — | `void` |

## AuthenticationClient
- Base path: `/password`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `adminResetPasswordPasswordAdminResetPost` | POST | `/password/admin/reset` | `AdminResetPasswordRequest` | `PasswordOperationResponse` |
| `adminSetPasswordPasswordAdminSetPost` | POST | `/password/admin/set` | `AdminSetPasswordRequest` | `PasswordOperationResponse` |
| `adminGetUserPasswordStatusPasswordAdminStatusUsernameGet` | GET | `/password/admin/status/{username}` | — | `PasswordStatusResponse` |
| `changePasswordPasswordChangePost` | POST | `/password/change` | `ChangePasswordRequest` | `PasswordOperationResponse` |
| `userManagerResetPasswordPasswordResetPost` | POST | `/password/reset` | `UserManagerResetPasswordRequest` | `PasswordOperationResponse` |
| `setInitialPasswordPasswordSetPost` | POST | `/password/set` | `SetPasswordRequest` | `PasswordOperationResponse` |
| `getPasswordStatusPasswordStatusGet` | GET | `/password/status` | — | `PasswordStatusResponse` |

## CourseContentKindsClient
- Base path: `/course-content-kinds`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseContentKindsCourseContentKindsGet` | GET | `/course-content-kinds` | — | `CourseContentKindList[]` |
| `createCourseContentKindsCourseContentKindsPost` | POST | `/course-content-kinds` | `CourseContentKindCreate` | `CourseContentKindGet` |
| `deleteCourseContentKindsCourseContentKindsIdDelete` | DELETE | `/course-content-kinds/{id}` | — | `void` |
| `getCourseContentKindsCourseContentKindsIdGet` | GET | `/course-content-kinds/{id}` | — | `CourseContentKindGet` |
| `updateCourseContentKindsCourseContentKindsIdPatch` | PATCH | `/course-content-kinds/{id}` | `CourseContentKindUpdate` | `CourseContentKindGet` |

## CourseContentTypesClient
- Base path: `/course-content-types`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseContentTypesCourseContentTypesGet` | GET | `/course-content-types` | — | `CourseContentTypeList[]` |
| `createCourseContentTypesCourseContentTypesPost` | POST | `/course-content-types` | `CourseContentTypeCreate` | `CourseContentTypeGet` |
| `deleteCourseContentTypesCourseContentTypesIdDelete` | DELETE | `/course-content-types/{id}` | — | `void` |
| `getCourseContentTypesCourseContentTypesIdGet` | GET | `/course-content-types/{id}` | — | `CourseContentTypeGet` |
| `updateCourseContentTypesCourseContentTypesIdPatch` | PATCH | `/course-content-types/{id}` | `CourseContentTypeUpdate` | `CourseContentTypeGet` |

## CourseContentsClient
- Base path: `/course-contents`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseContentsCourseContentsGet` | GET | `/course-contents` | — | `CourseContentList[]` |
| `createCourseContentsCourseContentsPost` | POST | `/course-contents` | `CourseContentCreate` | `CourseContentGet` |
| `getCourseDeploymentSummaryCourseContentsCoursesCourseIdDeploymentSummaryGet` | GET | `/course-contents/courses/{course_id}/deployment-summary` | — | `DeploymentSummary` |
| `getDeploymentStatusWithWorkflowCourseContentsDeploymentContentIdGet` | GET | `/course-contents/deployment/{content_id}` | — | `Record<string, unknown> & Record<string, unknown>` |
| `assignExampleToContentCourseContentsContentIdAssignExamplePost` | POST | `/course-contents/{content_id}/assign-example` | `computor_types__deployment__AssignExampleRequest` | `DeploymentWithHistory` |
| `getContentDeploymentCourseContentsContentIdDeploymentGet` | GET | `/course-contents/{content_id}/deployment` | — | `DeploymentWithHistory | null` |
| `unassignExampleFromContentCourseContentsContentIdExampleDelete` | DELETE | `/course-contents/{content_id}/example` | — | `Record<string, unknown> & Record<string, string>` |
| `getAvailableTeamsCourseContentsCourseContentIdSubmissionGroupsAvailableGet` | GET | `/course-contents/{course_content_id}/submission-groups/available` | — | `AvailableTeam[]` |
| `leaveMyTeamCourseContentsCourseContentIdSubmissionGroupsMyTeamDelete` | DELETE | `/course-contents/{course_content_id}/submission-groups/my-team` | — | `LeaveTeamResponse` |
| `getMyTeamCourseContentsCourseContentIdSubmissionGroupsMyTeamGet` | GET | `/course-contents/{course_content_id}/submission-groups/my-team` | — | `TeamResponse` |
| `createMyTeamCourseContentsCourseContentIdSubmissionGroupsMyTeamPost` | POST | `/course-contents/{course_content_id}/submission-groups/my-team` | `TeamCreate` | `TeamResponse` |
| `deleteCourseContentsCourseContentsIdDelete` | DELETE | `/course-contents/{id}` | — | `void` |
| `getCourseContentsCourseContentsIdGet` | GET | `/course-contents/{id}` | — | `CourseContentGet` |
| `updateCourseContentsCourseContentsIdPatch` | PATCH | `/course-contents/{id}` | `CourseContentUpdate` | `CourseContentGet` |
| `routeCourseContentsCourseContentsIdArchivePatch` | PATCH | `/course-contents/{id}/archive` | — | `void` |

## CourseFamiliesClient
- Base path: `/course-families`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseFamiliesCourseFamiliesGet` | GET | `/course-families` | — | `CourseFamilyList[]` |
| `createCourseFamiliesCourseFamiliesPost` | POST | `/course-families` | `CourseFamilyCreate` | `CourseFamilyGet` |
| `deleteCourseFamiliesCourseFamiliesIdDelete` | DELETE | `/course-families/{id}` | — | `void` |
| `getCourseFamiliesCourseFamiliesIdGet` | GET | `/course-families/{id}` | — | `CourseFamilyGet` |
| `updateCourseFamiliesCourseFamiliesIdPatch` | PATCH | `/course-families/{id}` | `CourseFamilyUpdate` | `CourseFamilyGet` |

## CourseGroupsClient
- Base path: `/course-groups`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseGroupsCourseGroupsGet` | GET | `/course-groups` | — | `CourseGroupList[]` |
| `createCourseGroupsCourseGroupsPost` | POST | `/course-groups` | `CourseGroupCreate` | `CourseGroupGet` |
| `deleteCourseGroupsCourseGroupsIdDelete` | DELETE | `/course-groups/{id}` | — | `void` |
| `getCourseGroupsCourseGroupsIdGet` | GET | `/course-groups/{id}` | — | `CourseGroupGet` |
| `updateCourseGroupsCourseGroupsIdPatch` | PATCH | `/course-groups/{id}` | `CourseGroupUpdate` | `CourseGroupGet` |

## CourseMemberCommentsClient
- Base path: `/course-member-comments`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCommentsCourseMemberCommentsGet` | GET | `/course-member-comments` | — | `CourseMemberCommentList[]` |
| `createCommentCourseMemberCommentsPost` | POST | `/course-member-comments` | `CommentCreate` | `CourseMemberCommentList[]` |
| `deleteCommentCourseMemberCommentsCourseMemberCommentIdDelete` | DELETE | `/course-member-comments/{course_member_comment_id}` | — | `CourseMemberCommentList[]` |
| `updateCommentCourseMemberCommentsCourseMemberCommentIdPatch` | PATCH | `/course-member-comments/{course_member_comment_id}` | `CommentUpdate` | `CourseMemberCommentList[]` |

## CourseMemberGradingsClient
- Base path: `/course-member-gradings`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseMemberGradingsEndpointCourseMemberGradingsGet` | GET | `/course-member-gradings` | — | `CourseMemberGradingsList[]` |
| `getCourseMemberGradingsEndpointCourseMemberGradingsCourseMemberIdGet` | GET | `/course-member-gradings/{course_member_id}` | — | `CourseMemberGradingsGet` |

## CourseMemberImportClient
- Base path: `/course-member-import`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `importMemberCourseMemberImportCourseIdPost` | POST | `/course-member-import/{course_id}` | `CourseMemberImportRequest` | `CourseMemberImportResponse` |

## CourseMembersClient
- Base path: `/course-members`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseMembersCourseMembersGet` | GET | `/course-members` | — | `CourseMemberList[]` |
| `createCourseMembersCourseMembersPost` | POST | `/course-members` | `CourseMemberCreate` | `CourseMemberGet` |
| `deleteCourseMembersCourseMembersIdDelete` | DELETE | `/course-members/{id}` | — | `void` |
| `getCourseMembersCourseMembersIdGet` | GET | `/course-members/{id}` | — | `CourseMemberGet` |
| `updateCourseMembersCourseMembersIdPatch` | PATCH | `/course-members/{id}` | `CourseMemberUpdate` | `CourseMemberGet` |

## CourseRolesClient
- Base path: `/course-roles`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCourseRolesCourseRolesGet` | GET | `/course-roles` | — | `CourseRoleList[]` |
| `getCourseRolesCourseRolesIdGet` | GET | `/course-roles/{id}` | — | `CourseRoleGet` |

## CoursesClient
- Base path: `/courses`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listCoursesCoursesGet` | GET | `/courses` | — | `CourseList[]` |
| `createCoursesCoursesPost` | POST | `/courses` | `CourseCreate` | `CourseGet` |
| `deleteCoursesCoursesIdDelete` | DELETE | `/courses/{id}` | — | `void` |
| `getCoursesCoursesIdGet` | GET | `/courses/{id}` | — | `CourseGet` |
| `updateCoursesCoursesIdPatch` | PATCH | `/courses/{id}` | `CourseUpdate` | `CourseGet` |

## ExampleRepositoriesClient
- Base path: `/example-repositories`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listExampleRepositoriesExampleRepositoriesGet` | GET | `/example-repositories` | — | `ExampleRepositoryList[]` |
| `createExampleRepositoriesExampleRepositoriesPost` | POST | `/example-repositories` | `ExampleRepositoryCreate` | `ExampleRepositoryGet` |
| `deleteExampleRepositoriesExampleRepositoriesIdDelete` | DELETE | `/example-repositories/{id}` | — | `void` |
| `getExampleRepositoriesExampleRepositoriesIdGet` | GET | `/example-repositories/{id}` | — | `ExampleRepositoryGet` |
| `updateExampleRepositoriesExampleRepositoriesIdPatch` | PATCH | `/example-repositories/{id}` | `ExampleRepositoryUpdate` | `ExampleRepositoryGet` |

## ExamplesClient
- Base path: `/examples`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listExamplesExamplesGet` | GET | `/examples` | — | `ExampleList[]` |
| `removeDependencyExamplesDependenciesDependencyIdDelete` | DELETE | `/examples/dependencies/{dependency_id}` | — | `void` |
| `downloadExampleVersionExamplesDownloadVersionIdGet` | GET | `/examples/download/{version_id}` | — | `ExampleDownloadResponse` |
| `uploadExampleExamplesUploadPost` | POST | `/examples/upload` | `ExampleUploadRequest` | `ExampleVersionGet` |
| `getVersionExamplesVersionsVersionIdGet` | GET | `/examples/versions/{version_id}` | — | `ExampleVersionGet` |
| `getExampleExamplesExampleIdGet` | GET | `/examples/{example_id}` | — | `ExampleGet` |
| `getExampleDependenciesExamplesExampleIdDependenciesGet` | GET | `/examples/{example_id}/dependencies` | — | `ExampleDependencyGet[]` |
| `createExampleDependencyExamplesExampleIdDependenciesPost` | POST | `/examples/{example_id}/dependencies` | `ExampleDependencyCreate` | `ExampleDependencyGet` |
| `deleteExampleDependencyExamplesExampleIdDependenciesDependencyIdDelete` | DELETE | `/examples/{example_id}/dependencies/{dependency_id}` | — | `void` |
| `downloadExampleLatestExamplesExampleIdDownloadGet` | GET | `/examples/{example_id}/download` | — | `ExampleDownloadResponse` |
| `listVersionsExamplesExampleIdVersionsGet` | GET | `/examples/{example_id}/versions` | — | `ExampleVersionList[]` |
| `createVersionExamplesExampleIdVersionsPost` | POST | `/examples/{example_id}/versions` | `ExampleVersionCreate` | `ExampleVersionGet` |

## ExtensionsClient
- Base path: `/extensions`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listExtensionsExtensionsGet` | GET | `/extensions` | — | `string[]` |
| `getExtensionMetadataExtensionsExtensionIdentityGet` | GET | `/extensions/{extension_identity}` | — | `ExtensionMetadata` |
| `downloadExtensionExtensionsExtensionIdentityDownloadGet` | GET | `/extensions/{extension_identity}/download` | — | `void` |
| `listExtensionVersionsExtensionsExtensionIdentityVersionsGet` | GET | `/extensions/{extension_identity}/versions` | — | `ExtensionVersionListResponse` |
| `publishExtensionVersionExtensionsExtensionIdentityVersionsPost` | POST | `/extensions/{extension_identity}/versions` | — | `ExtensionPublishResponse` |
| `updateExtensionVersionExtensionsExtensionIdentityVersionsVersionPatch` | PATCH | `/extensions/{extension_identity}/versions/{version}` | `ExtensionVersionYankRequest` | `ExtensionVersionDetail` |

## ExtensionsGettingStartedClient
- Base path: `/extensions-getting-started`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `getGettingStartedUrlExtensionsGettingStartedGet` | GET | `/extensions-getting-started` | — | `string` |

## ExtensionsPublicClient
- Base path: `/extensions-public`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `getPublicExtensionUrlExtensionsPublicGet` | GET | `/extensions-public` | — | `string` |

## GroupsClient
- Base path: `/groups`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listGroupsGroupsGet` | GET | `/groups` | — | `GroupList[]` |
| `createGroupsGroupsPost` | POST | `/groups` | `GroupCreate` | `GroupGet` |
| `deleteGroupsGroupsIdDelete` | DELETE | `/groups/{id}` | — | `void` |
| `getGroupsGroupsIdGet` | GET | `/groups/{id}` | — | `GroupGet` |
| `updateGroupsGroupsIdPatch` | PATCH | `/groups/{id}` | `GroupUpdate` | `GroupGet` |

## LanguagesClient
- Base path: `/languages`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listLanguagesLanguagesGet` | GET | `/languages` | — | `LanguageList[]` |
| `getLanguagesLanguagesIdGet` | GET | `/languages/{id}` | — | `LanguageGet` |

## LecturersClient
- Base path: `/lecturers`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `lecturerListCourseContentsEndpointLecturersCourseContentsGet` | GET | `/lecturers/course-contents` | — | `CourseContentLecturerList[]` |
| `lecturerGetCourseContentsEndpointLecturersCourseContentsCourseContentIdGet` | GET | `/lecturers/course-contents/{course_content_id}` | — | `CourseContentLecturerGet` |
| `assignExampleToCourseContentLecturersCourseContentsCourseContentIdAssignExamplePost` | POST | `/lecturers/course-contents/{course_content_id}/assign-example` | `computor_types__lecturer_deployments__AssignExampleRequest` | `AssignExampleResponse` |
| `unassignExampleFromCourseContentLecturersCourseContentsCourseContentIdDeploymentDelete` | DELETE | `/lecturers/course-contents/{course_content_id}/deployment` | — | `UnassignExampleResponse` |
| `getCourseContentDeploymentLecturersCourseContentsCourseContentIdDeploymentGet` | GET | `/lecturers/course-contents/{course_content_id}/deployment` | — | `DeploymentGet` |
| `syncMemberGitlabPermissionsEndpointLecturersCourseMembersCourseMemberIdSyncGitlabPost` | POST | `/lecturers/course-members/{course_member_id}/sync-gitlab` | `GitLabSyncRequest` | `GitLabSyncResult` |
| `lecturerListCoursesEndpointLecturersCoursesGet` | GET | `/lecturers/courses` | — | `CourseList[]` |
| `lecturerGetCoursesEndpointLecturersCoursesCourseIdGet` | GET | `/lecturers/courses/{course_id}` | — | `CourseGet` |
| `validateCourseContentBatchLecturersCoursesCourseIdValidatePost` | POST | `/lecturers/courses/{course_id}/validate` | `ContentValidationCreate` | `ContentValidationGet` |

## MessagesClient
- Base path: `/messages`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listMessagesMessagesGet` | GET | `/messages` | — | `MessageList[]` |
| `createMessageMessagesPost` | POST | `/messages` | `MessageCreate` | `MessageGet` |
| `deleteMessageMessagesIdDelete` | DELETE | `/messages/{id}` | — | `void` |
| `getMessageMessagesIdGet` | GET | `/messages/{id}` | — | `MessageGet` |
| `updateMessageMessagesIdPatch` | PATCH | `/messages/{id}` | `MessageUpdate` | `MessageGet` |
| `getMessageAuditMessagesIdAuditGet` | GET | `/messages/{id}/audit` | — | `void` |
| `markMessageUnreadMessagesIdReadsDelete` | DELETE | `/messages/{id}/reads` | — | `void` |
| `markMessageReadMessagesIdReadsPost` | POST | `/messages/{id}/reads` | — | `void` |

## MiscClient
- Base path: `/`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `getStatusHeadHead` | HEAD | `/` | — | `void` |

## OrganizationsClient
- Base path: `/organizations`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listOrganizationsOrganizationsGet` | GET | `/organizations` | — | `OrganizationList[]` |
| `createOrganizationsOrganizationsPost` | POST | `/organizations` | `OrganizationCreate` | `OrganizationGet` |
| `deleteOrganizationsOrganizationsIdDelete` | DELETE | `/organizations/{id}` | — | `void` |
| `getOrganizationsOrganizationsIdGet` | GET | `/organizations/{id}` | — | `OrganizationGet` |
| `updateOrganizationsOrganizationsIdPatch` | PATCH | `/organizations/{id}` | `OrganizationUpdate` | `OrganizationGet` |
| `routeOrganizationsOrganizationsIdArchivePatch` | PATCH | `/organizations/{id}/archive` | — | `void` |
| `patchOrganizationsTokenOrganizationsOrganizationIdTokenPatch` | PATCH | `/organizations/{organization_id}/token` | `OrganizationUpdateTokenUpdate` | `void` |

## ProfilesClient
- Base path: `/profiles`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listProfilesEndpointProfilesGet` | GET | `/profiles` | — | `ProfileList[]` |
| `createProfileEndpointProfilesPost` | POST | `/profiles` | `ProfileCreate` | `ProfileGet` |
| `deleteProfileEndpointProfilesIdDelete` | DELETE | `/profiles/{id}` | — | `void` |
| `getProfileEndpointProfilesIdGet` | GET | `/profiles/{id}` | — | `ProfileGet` |
| `updateProfileEndpointProfilesIdPatch` | PATCH | `/profiles/{id}` | `ProfileUpdate` | `ProfileGet` |

## ResultsClient
- Base path: `/results`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listResultsResultsGet` | GET | `/results` | — | `ResultList[]` |
| `createResultResultsPost` | POST | `/results` | `ResultCreate` | `ResultGet` |
| `deleteResultResultsResultIdDelete` | DELETE | `/results/{result_id}` | — | `void` |
| `getResultResultsResultIdGet` | GET | `/results/{result_id}` | — | `ResultGet` |
| `updateResultResultsResultIdPatch` | PATCH | `/results/{result_id}` | `ResultUpdate` | `ResultGet` |
| `listResultArtifactsEndpointResultsResultIdArtifactsGet` | GET | `/results/{result_id}/artifacts` | — | `ResultArtifactListItem[]` |
| `downloadResultArtifactsResultsResultIdArtifactsDownloadGet` | GET | `/results/{result_id}/artifacts/download` | — | `void` |
| `resultStatusResultsResultIdStatusGet` | GET | `/results/{result_id}/status` | — | `TaskStatus` |

## RolesClient
- Base path: `/role-claims`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listRoleClaimRoleClaimsGet` | GET | `/role-claims` | — | `RoleClaimList[]` |

## RolesClient
- Base path: `/roles`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listRolesRolesGet` | GET | `/roles` | — | `RoleList[]` |
| `getRolesRolesIdGet` | GET | `/roles/{id}` | — | `RoleGet` |

## ServiceTypesClient
- Base path: `/service-types`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listServiceTypesServiceTypesGet` | GET | `/service-types` | — | `ServiceTypeList[]` |
| `createServiceTypeServiceTypesPost` | POST | `/service-types` | `ServiceTypeCreate` | `ServiceTypeGet` |
| `getServiceTypeServiceTypesEntityIdGet` | GET | `/service-types/{entity_id}` | — | `ServiceTypeGet` |
| `updateServiceTypeServiceTypesEntityIdPatch` | PATCH | `/service-types/{entity_id}` | `ServiceTypeUpdate` | `ServiceTypeGet` |

## ServicesClient
- Base path: `/service-accounts`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listServicesEndpointServiceAccountsGet` | GET | `/service-accounts` | — | `ServiceGet[]` |
| `createServiceEndpointServiceAccountsPost` | POST | `/service-accounts` | `ServiceCreate` | `ServiceGet` |
| `deleteServiceEndpointServiceAccountsServiceIdDelete` | DELETE | `/service-accounts/{service_id}` | — | `void` |
| `getServiceEndpointServiceAccountsServiceIdGet` | GET | `/service-accounts/{service_id}` | — | `ServiceGet` |
| `updateServiceEndpointServiceAccountsServiceIdPatch` | PATCH | `/service-accounts/{service_id}` | `ServiceUpdate` | `ServiceGet` |
| `serviceHeartbeatEndpointServiceAccountsServiceIdHeartbeatPut` | PUT | `/service-accounts/{service_id}/heartbeat` | — | `void` |

## SessionsClient
- Base path: `/sessions`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listSessionsSessionsGet` | GET | `/sessions` | — | `SessionList[]` |
| `createSessionsSessionsPost` | POST | `/sessions` | `SessionCreate` | `SessionGet` |
| `getSessionStatsSessionsAdminStatsGet` | GET | `/sessions/admin/stats` | — | `void` |
| `listUserSessionsAdminSessionsAdminUsersUserIdGet` | GET | `/sessions/admin/users/{user_id}` | — | `SessionGet[]` |
| `revokeAllUserSessionsAdminSessionsAdminUsersUserIdAllDelete` | DELETE | `/sessions/admin/users/{user_id}/all` | — | `void` |
| `revokeSessionAdminSessionsAdminSessionIdDelete` | DELETE | `/sessions/admin/{session_id}` | — | `void` |
| `listMySessionsSessionsMeGet` | GET | `/sessions/me` | — | `SessionList[]` |
| `revokeAllMySessionsSessionsMeAllDelete` | DELETE | `/sessions/me/all` | — | `void` |
| `getCurrentSessionSessionsMeCurrentGet` | GET | `/sessions/me/current` | — | `SessionGet` |
| `revokeMySessionSessionsMeSessionIdDelete` | DELETE | `/sessions/me/{session_id}` | — | `void` |
| `deleteSessionsSessionsIdDelete` | DELETE | `/sessions/{id}` | — | `void` |
| `getSessionsSessionsIdGet` | GET | `/sessions/{id}` | — | `SessionGet` |
| `updateSessionsSessionsIdPatch` | PATCH | `/sessions/{id}` | `SessionUpdate` | `SessionGet` |

## StorageClient
- Base path: `/storage`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listBucketsStorageBucketsGet` | GET | `/storage/buckets` | — | `BucketInfo[]` |
| `createBucketStorageBucketsPost` | POST | `/storage/buckets` | `BucketCreate` | `BucketInfo` |
| `deleteBucketStorageBucketsBucketNameDelete` | DELETE | `/storage/buckets/{bucket_name}` | — | `void` |
| `getBucketStatsStorageBucketsBucketNameStatsGet` | GET | `/storage/buckets/{bucket_name}/stats` | — | `StorageUsageStats` |
| `copyObjectStorageCopyPost` | POST | `/storage/copy` | — | `void` |
| `downloadFileStorageDownloadObjectKeyGet` | GET | `/storage/download/{object_key}` | — | `void` |
| `listObjectsStorageObjectsGet` | GET | `/storage/objects` | — | `StorageObjectList[]` |
| `deleteObjectStorageObjectsObjectKeyDelete` | DELETE | `/storage/objects/{object_key}` | — | `void` |
| `getObjectInfoStorageObjectsObjectKeyGet` | GET | `/storage/objects/{object_key}` | — | `StorageObjectGet` |
| `generatePresignedUrlStoragePresignedUrlPost` | POST | `/storage/presigned-url` | `PresignedUrlRequest` | `PresignedUrlResponse` |
| `uploadFileStorageUploadPost` | POST | `/storage/upload` | — | `StorageObjectGet` |

## StudentProfilesClient
- Base path: `/student-profiles`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listStudentProfilesStudentProfilesGet` | GET | `/student-profiles` | — | `StudentProfileList[]` |
| `createStudentProfileStudentProfilesPost` | POST | `/student-profiles` | `StudentProfileCreate` | `StudentProfileGet` |
| `deleteStudentProfileStudentProfilesIdDelete` | DELETE | `/student-profiles/{id}` | — | `void` |
| `getStudentProfileStudentProfilesIdGet` | GET | `/student-profiles/{id}` | — | `StudentProfileGet` |
| `updateStudentProfileStudentProfilesIdPatch` | PATCH | `/student-profiles/{id}` | `StudentProfileUpdate` | `StudentProfileGet` |

## StudentsClient
- Base path: `/students`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `studentListCourseContentsEndpointStudentsCourseContentsGet` | GET | `/students/course-contents` | — | `CourseContentStudentList[]` |
| `studentGetCourseContentEndpointStudentsCourseContentsCourseContentIdGet` | GET | `/students/course-contents/{course_content_id}` | — | `CourseContentStudentGet` |
| `studentListCoursesEndpointStudentsCoursesGet` | GET | `/students/courses` | — | `CourseStudentList[]` |
| `studentGetCourseEndpointStudentsCoursesCourseIdGet` | GET | `/students/courses/{course_id}` | — | `CourseStudentGet` |

## SubmissionGroupMembersClient
- Base path: `/submission-group-members`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listSubmissionGroupMembersSubmissionGroupMembersGet` | GET | `/submission-group-members` | — | `SubmissionGroupMemberList[]` |
| `createSubmissionGroupMembersSubmissionGroupMembersPost` | POST | `/submission-group-members` | `SubmissionGroupMemberCreate` | `SubmissionGroupMemberGet` |
| `deleteSubmissionGroupMembersSubmissionGroupMembersIdDelete` | DELETE | `/submission-group-members/{id}` | — | `void` |
| `getSubmissionGroupMembersSubmissionGroupMembersIdGet` | GET | `/submission-group-members/{id}` | — | `SubmissionGroupMemberGet` |
| `updateSubmissionGroupMembersSubmissionGroupMembersIdPatch` | PATCH | `/submission-group-members/{id}` | `SubmissionGroupMemberUpdate` | `SubmissionGroupMemberGet` |

## SubmissionGroupsClient
- Base path: `/submission-groups`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listSubmissionGroupsSubmissionGroupsGet` | GET | `/submission-groups` | — | `SubmissionGroupList[]` |
| `createSubmissionGroupsSubmissionGroupsPost` | POST | `/submission-groups` | `SubmissionGroupCreate` | `SubmissionGroupGet` |
| `deleteSubmissionGroupsSubmissionGroupsIdDelete` | DELETE | `/submission-groups/{id}` | — | `void` |
| `getSubmissionGroupsSubmissionGroupsIdGet` | GET | `/submission-groups/{id}` | — | `SubmissionGroupGet` |
| `updateSubmissionGroupsSubmissionGroupsIdPatch` | PATCH | `/submission-groups/{id}` | `SubmissionGroupUpdate` | `SubmissionGroupGet` |
| `joinTeamSubmissionGroupsSubmissionGroupIdJoinPost` | POST | `/submission-groups/{submission_group_id}/join` | `JoinTeamRequest` | `JoinTeamResponse` |

## SubmissionsClient
- Base path: `/submissions`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listSubmissionArtifactsSubmissionsArtifactsGet` | GET | `/submissions/artifacts` | — | `SubmissionArtifactList[]` |
| `uploadSubmissionSubmissionsArtifactsPost` | POST | `/submissions/artifacts` | — | `SubmissionUploadResponseModel` |
| `downloadLatestSubmissionSubmissionsArtifactsDownloadGet` | GET | `/submissions/artifacts/download` | — | `void` |
| `getSubmissionArtifactSubmissionsArtifactsArtifactIdGet` | GET | `/submissions/artifacts/{artifact_id}` | — | `SubmissionArtifactGet` |
| `updateSubmissionArtifactSubmissionsArtifactsArtifactIdPatch` | PATCH | `/submissions/artifacts/{artifact_id}` | `SubmissionArtifactUpdate` | `SubmissionArtifactGet` |
| `downloadSubmissionArtifactSubmissionsArtifactsArtifactIdDownloadGet` | GET | `/submissions/artifacts/{artifact_id}/download` | — | `void` |
| `listArtifactGradesSubmissionsArtifactsArtifactIdGradesGet` | GET | `/submissions/artifacts/{artifact_id}/grades` | — | `SubmissionGradeListItem[]` |
| `createArtifactGradeEndpointSubmissionsArtifactsArtifactIdGradesPost` | POST | `/submissions/artifacts/{artifact_id}/grades` | `SubmissionGradeCreate` | `SubmissionGradeDetail` |
| `listArtifactReviewsSubmissionsArtifactsArtifactIdReviewsGet` | GET | `/submissions/artifacts/{artifact_id}/reviews` | — | `SubmissionReviewListItem[]` |
| `createArtifactReviewSubmissionsArtifactsArtifactIdReviewsPost` | POST | `/submissions/artifacts/{artifact_id}/reviews` | `SubmissionReviewCreate` | `SubmissionReviewListItem` |
| `createTestResultSubmissionsArtifactsArtifactIdTestPost` | POST | `/submissions/artifacts/{artifact_id}/test` | `ResultCreate` | `ResultList` |
| `listArtifactTestResultsSubmissionsArtifactsArtifactIdTestsGet` | GET | `/submissions/artifacts/{artifact_id}/tests` | — | `ResultList[]` |
| `deleteArtifactGradeSubmissionsGradesGradeIdDelete` | DELETE | `/submissions/grades/{grade_id}` | — | `void` |
| `updateArtifactGradeSubmissionsGradesGradeIdPatch` | PATCH | `/submissions/grades/{grade_id}` | `SubmissionGradeUpdate` | `SubmissionGradeDetail` |
| `deleteArtifactReviewSubmissionsReviewsReviewIdDelete` | DELETE | `/submissions/reviews/{review_id}` | — | `void` |
| `updateArtifactReviewSubmissionsReviewsReviewIdPatch` | PATCH | `/submissions/reviews/{review_id}` | `SubmissionReviewUpdate` | `SubmissionReviewListItem` |
| `updateTestResultSubmissionsTestsTestIdPatch` | PATCH | `/submissions/tests/{test_id}` | `ResultUpdate` | `ResultList` |

## SystemClient
- Base path: `/system`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `syncDocumentsRepositorySystemCourseFamiliesCourseFamilyIdSyncDocumentsPost` | POST | `/system/course-families/{course_family_id}/sync-documents` | — | `Record<string, unknown> & Record<string, unknown>` |
| `generateAssignmentsSystemCoursesCourseIdGenerateAssignmentsPost` | POST | `/system/courses/{course_id}/generate-assignments` | `GenerateAssignmentsRequest` | `GenerateAssignmentsResponse` |
| `generateStudentTemplateSystemCoursesCourseIdGenerateStudentTemplatePost` | POST | `/system/courses/{course_id}/generate-student-template` | `GenerateTemplateRequest` | `GenerateTemplateResponse` |
| `getCourseGitlabStatusSystemCoursesCourseIdGitlabStatusGet` | GET | `/system/courses/{course_id}/gitlab-status` | — | `Record<string, unknown> & Record<string, unknown>` |
| `createCourseFamilyAsyncSystemDeployCourseFamiliesPost` | POST | `/system/deploy/course-families` | `CourseFamilyTaskRequest` | `TaskResponse` |
| `createCourseAsyncSystemDeployCoursesPost` | POST | `/system/deploy/courses` | `CourseTaskRequest` | `TaskResponse` |
| `createOrganizationAsyncSystemDeployOrganizationsPost` | POST | `/system/deploy/organizations` | `OrganizationTaskRequest` | `TaskResponse` |
| `createHierarchySystemHierarchyCreatePost` | POST | `/system/hierarchy/create` | `Record<string, unknown> & Record<string, unknown>` | `Record<string, unknown> & Record<string, unknown>` |
| `getHierarchyStatusSystemHierarchyStatusWorkflowIdGet` | GET | `/system/hierarchy/status/{workflow_id}` | — | `Record<string, unknown> & Record<string, unknown>` |

## TasksClient
- Base path: `/tasks`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listTasksTasksGet` | GET | `/tasks` | — | `Record<string, unknown> & Record<string, unknown>` |
| `submitTaskTasksSubmitPost` | POST | `/tasks/submit` | `TaskSubmission` | `Record<string, unknown> & Record<string, string>` |
| `listTaskTypesTasksTypesGet` | GET | `/tasks/types` | — | `string[]` |
| `getWorkerStatusTasksWorkersStatusGet` | GET | `/tasks/workers/status` | — | `Record<string, unknown> & Record<string, unknown>` |
| `deleteTaskTasksTaskIdDelete` | DELETE | `/tasks/{task_id}` | — | `void` |
| `getTaskTasksTaskIdGet` | GET | `/tasks/{task_id}` | — | `TaskInfo` |
| `cancelTaskTasksTaskIdCancelDelete` | DELETE | `/tasks/{task_id}/cancel` | — | `void` |
| `getTaskResultTasksTaskIdResultGet` | GET | `/tasks/{task_id}/result` | — | `TaskResult` |
| `getTaskStatusTasksTaskIdStatusGet` | GET | `/tasks/{task_id}/status` | — | `TaskInfo` |

## TestsClient
- Base path: `/tests`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `createTestRunTestsPost` | POST | `/tests` | `TestCreate` | `ResultList` |
| `getTestStatusTestsStatusResultIdGet` | GET | `/tests/status/{result_id}` | — | `void` |

## TokensClient
- Base path: `/api-tokens`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listTokensEndpointApiTokensGet` | GET | `/api-tokens` | — | `ApiTokenGet[]` |
| `createTokenEndpointApiTokensPost` | POST | `/api-tokens` | `ApiTokenCreate` | `ApiTokenCreateResponse` |
| `createTokenAdminEndpointApiTokensAdminCreatePost` | POST | `/api-tokens/admin/create` | `ApiTokenAdminCreate` | `ApiTokenCreateResponse` |
| `updateTokenAdminEndpointApiTokensAdminTokenIdPatch` | PATCH | `/api-tokens/admin/{token_id}` | `ApiTokenUpdate` | `ApiTokenGet` |
| `revokeTokenEndpointApiTokensTokenIdDelete` | DELETE | `/api-tokens/{token_id}` | — | `void` |
| `getTokenEndpointApiTokensTokenIdGet` | GET | `/api-tokens/{token_id}` | — | `ApiTokenGet` |

## TutorsClient
- Base path: `/tutors`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `downloadCourseContentReferenceTutorsCourseContentsCourseContentIdReferenceGet` | GET | `/tutors/course-contents/{course_content_id}/reference` | — | `void` |
| `tutorListCourseMembersEndpointTutorsCourseMembersGet` | GET | `/tutors/course-members` | — | `TutorCourseMemberList[]` |
| `tutorGetCourseMembersEndpointTutorsCourseMembersCourseMemberIdGet` | GET | `/tutors/course-members/{course_member_id}` | — | `TutorCourseMemberGet` |
| `tutorListCourseContentsEndpointTutorsCourseMembersCourseMemberIdCourseContentsGet` | GET | `/tutors/course-members/{course_member_id}/course-contents` | — | `CourseContentStudentList[]` |
| `tutorGetCourseContentsEndpointTutorsCourseMembersCourseMemberIdCourseContentsCourseContentIdGet` | GET | `/tutors/course-members/{course_member_id}/course-contents/{course_content_id}` | — | `CourseContentStudentGet` |
| `tutorUpdateCourseContentsEndpointTutorsCourseMembersCourseMemberIdCourseContentsCourseContentIdPatch` | PATCH | `/tutors/course-members/{course_member_id}/course-contents/{course_content_id}` | `TutorGradeCreate` | `TutorGradeResponse` |
| `tutorListCoursesEndpointTutorsCoursesGet` | GET | `/tutors/courses` | — | `CourseTutorList[]` |
| `tutorGetCoursesEndpointTutorsCoursesCourseIdGet` | GET | `/tutors/courses/{course_id}` | — | `CourseTutorGet` |
| `tutorListSubmissionGroupsEndpointTutorsSubmissionGroupsGet` | GET | `/tutors/submission-groups` | — | `TutorSubmissionGroupList[]` |
| `tutorGetSubmissionGroupEndpointTutorsSubmissionGroupsSubmissionGroupIdGet` | GET | `/tutors/submission-groups/{submission_group_id}` | — | `TutorSubmissionGroupGet` |

## UserClient
- Base path: `/user`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `getCurrentUserEndpointUserGet` | GET | `/user` | — | `UserGet` |
| `registerCurrentUserCourseAccountUserCoursesCourseIdRegisterPost` | POST | `/user/courses/{course_id}/register` | `CourseMemberProviderAccountUpdate` | `CourseMemberReadinessStatus` |
| `validateCurrentUserCourseUserCoursesCourseIdValidatePost` | POST | `/user/courses/{course_id}/validate` | `CourseMemberValidationRequest` | `CourseMemberReadinessStatus` |
| `setUserPasswordEndpointUserPasswordPost` | POST | `/user/password` | `UserPassword` | `void` |
| `getCourseViewsForCurrentUserUserViewsGet` | GET | `/user/views` | — | `string[]` |
| `getCourseViewsForCurrentUserByCourseUserViewsCourseIdGet` | GET | `/user/views/{course_id}` | — | `string[]` |

## UserClient
- Base path: `/user-roles`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listUserRolesUserRolesGet` | GET | `/user-roles` | — | `UserRoleList[]` |
| `createUserRoleUserRolesPost` | POST | `/user-roles` | `UserRoleCreate` | `UserRoleGet` |
| `deleteUserRoleEndpointUserRolesUsersUserIdRolesRoleIdDelete` | DELETE | `/user-roles/users/{user_id}/roles/{role_id}` | — | `Record<string, unknown> & Record<string, unknown>` |
| `getUserRoleEndpointUserRolesUsersUserIdRolesRoleIdGet` | GET | `/user-roles/users/{user_id}/roles/{role_id}` | — | `UserRoleGet` |

## UsersClient
- Base path: `/users`
- Note: custom operations discovered from OpenAPI schema

| TS Method | HTTP | Path | Request | Response |
| --- | --- | --- | --- | --- |
| `listUsersUsersGet` | GET | `/users` | — | `UserList[]` |
| `createUsersUsersPost` | POST | `/users` | `UserCreate` | `UserGet` |
| `deleteUsersUsersIdDelete` | DELETE | `/users/{id}` | — | `void` |
| `getUsersUsersIdGet` | GET | `/users/{id}` | — | `UserGet` |
| `updateUsersUsersIdPatch` | PATCH | `/users/{id}` | `UserUpdate` | `UserGet` |
| `routeUsersUsersIdArchivePatch` | PATCH | `/users/{id}/archive` | — | `void` |
