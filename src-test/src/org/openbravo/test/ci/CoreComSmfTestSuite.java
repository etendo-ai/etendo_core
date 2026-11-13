package org.openbravo.test.ci;

import org.junit.platform.suite.api.SelectClasses;
import org.junit.platform.suite.api.Suite;

@Suite
@SelectClasses({
    com.smf.jobs.TestActionHookCall.class,
    com.smf.jobs.defaults.CloneOrderHookTest.class,
    com.smf.jobs.defaults.PostTest.class,
    com.smf.jobs.defaults.ProcessInvoicesDefaultsTest.class,
    com.smf.jobs.defaults.ProcessInvoicesTest.class,
    com.smf.jobs.defaults.ProcessOrdersDefaultsTest.class,
    com.smf.jobs.defaults.ProcessOrdersTest.class,
    com.smf.jobs.defaults.ProcessShipmentDefaultsTest.class,
    com.smf.jobs.defaults.ProcessShipmentTest.class,
    com.smf.jobs.defaults.invoices.CreateFromOrderTest.class,
    com.smf.jobs.defaults.invoices.CreateFromOrdersHQLTransformerTest.class,
    com.smf.securewebservices.InitializeSingletonTest.class,
    com.smf.securewebservices.SWSDataSourceServiceTest.class,
    com.smf.securewebservices.cors.AllowCrossDomainsTest.class,
    com.smf.securewebservices.provider.ContextInfoServletTest.class,
    com.smf.securewebservices.rsql.OBRestUtilsMapParametersTest.class,
    com.smf.securewebservices.rsql.OBRestUtilsTest.class,
    com.smf.securewebservices.service.BaseActionTest.class,
    com.smf.securewebservices.service.BaseWebServiceTest.class,
    com.smf.securewebservices.service.DataSourceServletTest.class,
    com.smf.securewebservices.service.JsonDalWebServiceParameterTest.class,
    com.smf.securewebservices.service.JsonDalWebServiceTest.class,
    com.smf.securewebservices.service.KernelServletTest.class,
    com.smf.securewebservices.service.SecureLoginServletTest.class,
    com.smf.securewebservices.service.SecureWebServiceServletTest.class,
    com.smf.securewebservices.utils.JSONStreamWriterTest.class,
    com.smf.securewebservices.utils.ResultTest.class,
    com.smf.securewebservices.utils.SecureWebServicesUtilsAdditionalTests.class,
    com.smf.securewebservices.utils.SecureWebServicesUtilsTest.class,
})
public class CoreComSmfTestSuite {
}
